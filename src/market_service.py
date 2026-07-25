"""Application service joining market data, persistence, and analytics."""

from __future__ import annotations

import threading
import time
from typing import Any

from market_data import provider
from market_db import DEFAULT_OWNER, MarketDatabase
from prediction import MODEL_VERSION, backtest, predict_trends, risk_metrics, simulate_probability_strategy


class MarketService:
    def __init__(self, database: MarketDatabase | None = None, data_provider=None):
        self.db = database or MarketDatabase()
        self.provider = data_provider or provider
        self._analysis_cache: dict[int, tuple[float, dict[str, Any]]] = {}
        self._refresh_locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _asset_lock(self, asset_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._refresh_locks.setdefault(asset_id, threading.Lock())

    def search(self, query: str, asset_class: str | None, subclass: str | None) -> list[dict[str, Any]]:
        if asset_class not in {None, "stock", "fund"}:
            raise ValueError("Unsupported asset class")
        results = self.provider.search(query.strip(), asset_class, subclass)
        return [self._public_asset(item) for item in results]

    @staticmethod
    def _public_asset(asset: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "id",
            "symbol",
            "provider_symbol",
            "name",
            "asset_class",
            "subclass",
            "market",
            "exchange",
            "currency",
            "timezone",
            "source",
            "status",
        }
        return {key: value for key, value in asset.items() if key in allowed}

    def ensure_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        asset = self.db.ensure_asset(payload)
        return self._public_asset(asset)

    def add_watchlist(self, payload: dict[str, Any], owner_id: str = DEFAULT_OWNER) -> dict[str, Any]:
        asset_payload = payload.get("asset") if isinstance(payload.get("asset"), dict) else payload
        asset = self.db.ensure_asset(asset_payload)
        self.db.add_watchlist(int(asset["id"]), owner_id, str(payload.get("group_name") or "默认"))
        analysis = self.refresh_asset(int(asset["id"]))
        return analysis

    def add_transaction(self, payload: dict[str, Any], owner_id: str = DEFAULT_OWNER) -> dict[str, Any]:
        if isinstance(payload.get("asset"), dict):
            asset = self.db.ensure_asset(payload["asset"])
            transaction_payload = {**payload, "asset_id": asset["id"]}
        else:
            transaction_payload = payload
        transaction = self.db.add_transaction(transaction_payload, owner_id)
        asset_id = int(transaction["asset_id"])
        if not self.db.get_quote(asset_id):
            self.refresh_asset(asset_id)
        return transaction

    def refresh_asset(self, asset_id: int, force: bool = False) -> dict[str, Any]:
        asset = self.db.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")
        lock = self._asset_lock(asset_id)
        with lock:
            cached = self._analysis_cache.get(asset_id)
            if cached and not force and time.time() - cached[0] < 25:
                return cached[1]

            quote = self.provider.quote(asset)
            self.db.upsert_quote(asset_id, quote)
            existing_bars = self.db.get_daily_bars(asset_id, limit=30)
            if force or len(existing_bars) < 25:
                bars = self.provider.history(asset, days=520)
                self.db.upsert_daily_bars(asset_id, bars)
            bars = self.db.get_daily_bars(asset_id, limit=520)
            prices = [float(bar["close"]) for bar in bars]
            predictions = predict_trends(prices, float(quote["price"]))
            if predictions:
                self.db.save_predictions(
                    asset_id,
                    str(quote["quote_time"]),
                    float(quote["price"]),
                    predictions,
                    MODEL_VERSION,
                )
            analysis = self._compose_asset(asset, bars, predictions)
            self._analysis_cache[asset_id] = (time.time(), analysis)
            return analysis

    def _compose_asset(
        self,
        asset: dict[str, Any],
        bars: list[dict[str, Any]] | None = None,
        predictions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        asset_id = int(asset["id"])
        quote = self.db.get_quote(asset_id)
        bars = bars if bars is not None else self.db.get_daily_bars(asset_id, limit=520)
        prices = [float(bar["close"]) for bar in bars]
        if predictions is None:
            predictions = self.db.latest_predictions(asset_id)
        output = {
            **self._public_asset(asset),
            "quote": quote,
            "predictions": predictions,
            "risk": risk_metrics(prices),
            "performance": backtest(prices),
            "simulation": simulate_probability_strategy(prices),
            "history": [
                {
                    "date": bar["bar_date"],
                    "close": bar["close"],
                    "volume": bar["volume"],
                }
                for bar in bars[-260:]
            ],
        }
        return output

    def get_asset_detail(self, asset_id: int, refresh: bool = False) -> dict[str, Any]:
        asset = self.db.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")
        if refresh or not self.db.get_quote(asset_id) or len(self.db.get_daily_bars(asset_id, 25)) < 25:
            return self.refresh_asset(asset_id, force=refresh)
        return self._compose_asset(asset)

    def refresh_tracked(self, owner_id: str = DEFAULT_OWNER) -> list[dict[str, Any]]:
        results = []
        for asset_id in self.db.tracked_asset_ids(owner_id):
            try:
                results.append(self.refresh_asset(asset_id))
            except Exception as error:
                asset = self.db.get_asset(asset_id) or {"id": asset_id}
                results.append({**self._public_asset(asset), "error": str(error)})
        return results

    def dashboard(self, owner_id: str = DEFAULT_OWNER, refresh_missing: bool = True) -> dict[str, Any]:
        watchlist = self.db.list_watchlist(owner_id)
        positions = self.db.calculate_positions(owner_id)
        if refresh_missing:
            missing_ids = {
                int(item["id"])
                for item in [*watchlist, *positions]
                if item.get("price") is None and item.get("current_price") is None
            }
            for asset_id in missing_ids:
                try:
                    self.refresh_asset(asset_id)
                except Exception:
                    pass
            if missing_ids:
                watchlist = self.db.list_watchlist(owner_id)
                positions = self.db.calculate_positions(owner_id)

        for item in watchlist:
            item["predictions"] = self.db.latest_predictions(int(item["id"]))
        for item in positions:
            item["predictions"] = self.db.latest_predictions(int(item["id"]))
        held_ids = {int(item["id"]) for item in positions}
        watchlist_only = [item for item in watchlist if int(item["id"]) not in held_ids]
        return {
            "positions": positions,
            "watchlist": watchlist,
            "watchlist_only": watchlist_only,
            "summary": self.db.portfolio_summary(owner_id),
            "tracked_count": len(set(self.db.tracked_asset_ids(owner_id))),
        }


service = MarketService()

