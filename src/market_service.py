"""Application service joining market data, persistence, and analytics."""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime
from typing import Any

from investment_habits import derive_investment_habits
from market_data import MarketDataError, provider
from market_db import DEFAULT_OWNER, MarketDatabase
from prediction import (
    MODEL_VERSION,
    OTC_FUND_MODEL_VERSION,
    backtest,
    backtest_otc_fund_direction,
    predict_otc_fund_direction,
    predict_trends,
    risk_metrics,
    simulate_probability_strategy,
)


class MarketService:
    def __init__(self, database: MarketDatabase | None = None, data_provider=None):
        self.db = database or MarketDatabase()
        self.provider = data_provider or provider
        self._analysis_cache: dict[int, tuple[float, dict[str, Any]]] = {}
        self._refresh_locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._sync_investment_habits_safely()

    def sync_investment_habits(self, owner_id: str = DEFAULT_OWNER) -> list[dict[str, Any]]:
        habits = derive_investment_habits(
            self.db.list_watchlist(owner_id),
            self.db.calculate_positions(owner_id),
            self.db.list_transactions(owner_id),
        )
        self.db.replace_investment_habits(habits, owner_id)
        return self.db.list_investment_habits(owner_id)

    def _sync_investment_habits_safely(
        self,
        owner_id: str = DEFAULT_OWNER,
    ) -> list[dict[str, Any]]:
        try:
            return self.sync_investment_habits(owner_id)
        except Exception:
            logging.getLogger(__name__).exception("Investment habit sync failed")
            return []

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
        self._sync_investment_habits_safely(owner_id)
        analysis = self.refresh_asset(int(asset["id"]))
        return analysis

    def remove_watchlist(self, asset_id: int, owner_id: str = DEFAULT_OWNER) -> None:
        self.db.remove_watchlist(asset_id, owner_id)
        self._sync_investment_habits_safely(owner_id)

    def add_transaction(self, payload: dict[str, Any], owner_id: str = DEFAULT_OWNER) -> dict[str, Any]:
        if isinstance(payload.get("asset"), dict):
            asset = self.db.ensure_asset(payload["asset"])
            transaction_payload = {**payload, "asset_id": asset["id"]}
        else:
            transaction_payload = payload
        transaction = self.db.add_transaction(transaction_payload, owner_id)
        self._sync_investment_habits_safely(owner_id)
        asset_id = int(transaction["asset_id"])
        if not self.db.get_quote(asset_id):
            self.refresh_asset(asset_id)
        return transaction

    @staticmethod
    def _import_queries(symbol: str, name: str) -> list[str]:
        queries = []
        if symbol:
            queries.append(symbol)
            if symbol.isdigit():
                queries.extend([symbol.zfill(6), symbol.zfill(5), symbol.zfill(4)])
        if name:
            queries.append(name)
        return list(dict.fromkeys(query for query in queries if query))

    @staticmethod
    def _import_name_key(value: Any) -> str:
        """Normalize harmless fund-name variants without merging share classes."""

        text = re.sub(r"[\s_\-—（）()：:/.·]", "", str(value or "")).casefold()
        return text.replace("发起式", "").replace("发起", "")

    def _resolve_import_asset(self, row: dict[str, Any]) -> dict[str, Any]:
        symbol = str(row.get("symbol") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        asset_class = str(row.get("asset_class") or "").strip() or None
        subclass = str(row.get("subclass") or "").strip() or None
        candidates: dict[str, dict[str, Any]] = {}
        for constrained in (True, False):
            for query in self._import_queries(symbol, name):
                results = self.search(
                    query,
                    asset_class if constrained else None,
                    subclass if constrained else None,
                )
                for item in results:
                    candidates[str(item.get("provider_symbol") or item.get("symbol"))] = item
            if candidates:
                break
        if not candidates:
            raise ValueError(f"未找到资产：{symbol or name}")

        desired_symbols = {symbol}
        if symbol.isdigit():
            desired_symbols.update({symbol.zfill(6), symbol.zfill(5), symbol.zfill(4)})
        exact_symbol = [
            item for item in candidates.values()
            if str(item.get("symbol") or "").upper() in desired_symbols
            or str(item.get("provider_symbol") or "").upper().split(".")[0] in desired_symbols
        ]
        if len(exact_symbol) == 1:
            return exact_symbol[0]
        exact_name = [item for item in candidates.values() if name and str(item.get("name") or "").casefold() == name.casefold()]
        if len(exact_name) == 1:
            return exact_name[0]
        name_key = self._import_name_key(name)
        normalized_name = [
            item for item in candidates.values()
            if name_key and self._import_name_key(item.get("name")) == name_key
        ]
        if len(normalized_name) == 1:
            return normalized_name[0]
        if len(candidates) == 1:
            return next(iter(candidates.values()))
        raise ValueError(f"匹配到多个资产，请在文件中补充准确代码：{symbol or name}")

    @staticmethod
    def _import_occurred_at(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = text.replace("/", "-")
        try:
            datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"无法识别日期：{text}") from error
        return normalized

    def import_portfolio_rows(
        self,
        rows: list[dict[str, Any]],
        target: str,
        owner_id: str = DEFAULT_OWNER,
    ) -> dict[str, Any]:
        if target not in {"holdings", "watchlist"}:
            raise ValueError("导入目标必须是持有或自选")
        imported = []
        errors = []
        seen_watchlist_ids: set[int] = set()
        for index, row in enumerate(rows, start=1):
            label = str(row.get("symbol") or row.get("name") or f"第 {index} 行")
            try:
                matched = self._resolve_import_asset(row)
                asset = self.db.ensure_asset(matched)
                asset_id = int(asset["id"])
                if target == "watchlist":
                    if asset_id in seen_watchlist_ids:
                        continue
                    self.db.add_watchlist(asset_id, owner_id)
                    seen_watchlist_ids.add(asset_id)
                else:
                    quantity = float(row.get("quantity") or 0)
                    cost_price = float(row.get("cost_price") or 0)
                    if quantity <= 0 or cost_price <= 0:
                        raise ValueError("持仓需要大于 0 的数量/份额和平均成本价")
                    occurred_at = self._import_occurred_at(row.get("occurred_at"))
                    transaction_payload = {
                        "asset_id": asset_id,
                        "transaction_type": "subscribe" if asset.get("subclass") == "otc" else "buy",
                        "quantity": quantity,
                        "price": cost_price,
                        "currency": row.get("currency") or asset.get("currency"),
                        "note": "从图片/文件一键导入",
                    }
                    if occurred_at:
                        transaction_payload["occurred_at"] = occurred_at
                    self.db.add_transaction(transaction_payload, owner_id)
                imported.append({
                    "id": asset_id,
                    "symbol": asset["symbol"],
                    "name": asset["name"],
                    "target": target,
                })
            except (TypeError, ValueError) as error:
                errors.append({"row": index, "label": label, "error": str(error)})
            except Exception:
                errors.append({"row": index, "label": label, "error": "行情匹配暂时不可用"})
        self._sync_investment_habits_safely(owner_id)
        return {
            "target": target,
            "total": len(rows),
            "imported_count": len(imported),
            "failed_count": len(errors),
            "imported": imported,
            "errors": errors,
        }

    def _official_nav_from_history(self, asset: dict[str, Any]) -> dict[str, Any] | None:
        if asset.get("subclass") != "otc":
            return None
        bars = [
            bar
            for bar in self.db.get_daily_bars(int(asset["id"]), limit=10)
            if bar.get("source") != "demo"
        ]
        if not bars:
            return None
        latest = bars[-1]
        previous_close = bars[-2]["close"] if len(bars) > 1 else None
        return {
            "price": latest["close"],
            "previous_close": previous_close,
            "currency": asset.get("currency") or "CNY",
            "quote_time": f"{latest['bar_date']}T20:00:00+08:00",
            "source": latest.get("source") or "official-history",
            "is_delayed": True,
        }

    def refresh_asset(self, asset_id: int, force: bool = False) -> dict[str, Any]:
        asset = self.db.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")
        lock = self._asset_lock(asset_id)
        with lock:
            cached = self._analysis_cache.get(asset_id)
            if cached and not force and time.time() - cached[0] < 25:
                return cached[1]

            try:
                quote = self.provider.quote(asset)
            except MarketDataError:
                quote = self._official_nav_from_history(asset)
                if not quote:
                    raise
            self.db.upsert_quote(asset_id, quote)
            existing_bars = self.db.get_daily_bars(asset_id, limit=30)
            if force or len(existing_bars) < 25:
                try:
                    bars = self.provider.history(asset, days=520)
                    self.db.upsert_daily_bars(asset_id, bars)
                except MarketDataError:
                    if asset.get("subclass") != "otc" or not existing_bars:
                        raise
            bars = self.db.get_daily_bars(asset_id, limit=520)
            prices = [float(bar["close"]) for bar in bars]
            is_otc_fund = asset.get("subclass") == "otc"
            predictions = (
                predict_otc_fund_direction(prices, float(quote["price"]))
                if is_otc_fund
                else predict_trends(prices, float(quote["price"]))
            )
            if predictions:
                self.db.save_predictions(
                    asset_id,
                    str(quote["quote_time"]),
                    float(quote["price"]),
                    predictions,
                    OTC_FUND_MODEL_VERSION if is_otc_fund else MODEL_VERSION,
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
        is_otc_fund = asset.get("subclass") == "otc"
        output = {
            **self._public_asset(asset),
            "quote": quote,
            "predictions": predictions,
            "risk": risk_metrics(prices),
            "performance": (
                backtest_otc_fund_direction(prices) if is_otc_fund else backtest(prices)
            ),
            "simulation": {} if is_otc_fund else simulate_probability_strategy(prices),
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
        watchlist_ids = {int(item["id"]) for item in watchlist}
        missing_watchlist = [item for item in positions if int(item["id"]) not in watchlist_ids]
        for item in missing_watchlist:
            self.db.add_watchlist(int(item["id"]), owner_id)
        if missing_watchlist:
            self._sync_investment_habits_safely(owner_id)
            watchlist = self.db.list_watchlist(owner_id)
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
            "investment_habits": self.db.list_investment_habits(owner_id),
        }


service = MarketService()
