"""SQLite persistence for the local investment workspace."""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


DEFAULT_OWNER = "local"
ASSET_CLASSES = {"stock", "fund"}
ASSET_SUBCLASSES = {"cn", "hk", "us", "exchange_traded", "otc"}
TRANSACTION_TYPES = {
    "buy",
    "sell",
    "subscribe",
    "redeem",
    "dividend",
    "fee",
    "split",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MarketDatabase:
    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("MARKET_DB_PATH")
        self.path = Path(configured) if configured else Path(__file__).parent / "data" / "investment.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            provider_symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            asset_class TEXT NOT NULL CHECK (asset_class IN ('stock', 'fund')),
            subclass TEXT NOT NULL,
            market TEXT NOT NULL,
            exchange TEXT NOT NULL DEFAULT '',
            currency TEXT NOT NULL DEFAULT 'CNY',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            source TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(asset_class, market, provider_symbol)
        );

        CREATE TABLE IF NOT EXISTS watchlists (
            owner_id TEXT NOT NULL DEFAULT 'local',
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            group_name TEXT NOT NULL DEFAULT '默认',
            created_at TEXT NOT NULL,
            PRIMARY KEY(owner_id, asset_id)
        );

        CREATE TABLE IF NOT EXISTS latest_quotes (
            asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
            price REAL NOT NULL,
            previous_close REAL,
            change_value REAL,
            change_percent REAL,
            currency TEXT NOT NULL,
            quote_time TEXT NOT NULL,
            received_at TEXT NOT NULL,
            source TEXT NOT NULL,
            is_delayed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS daily_bars (
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            bar_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL NOT NULL,
            volume REAL,
            source TEXT NOT NULL,
            PRIMARY KEY(asset_id, bar_date)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL DEFAULT 'local',
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
            transaction_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            fees REAL NOT NULL DEFAULT 0,
            taxes REAL NOT NULL DEFAULT 0,
            cash_amount REAL NOT NULL DEFAULT 0,
            currency TEXT NOT NULL,
            fx_rate REAL NOT NULL DEFAULT 1,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_owner_asset_time
            ON transactions(owner_id, asset_id, occurred_at, created_at);

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            generated_at TEXT NOT NULL,
            quote_time TEXT NOT NULL,
            base_price REAL NOT NULL,
            horizon_days INTEGER NOT NULL,
            probability_up REAL NOT NULL,
            probability_flat REAL NOT NULL,
            probability_down REAL NOT NULL,
            expected_low REAL,
            expected_high REAL,
            confidence TEXT NOT NULL,
            model_version TEXT NOT NULL,
            UNIQUE(asset_id, quote_time, horizon_days, model_version)
        );

        CREATE TABLE IF NOT EXISTS investment_notes (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL DEFAULT 'local',
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            note_type TEXT NOT NULL DEFAULT 'thesis',
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        with self.connect() as connection:
            connection.executescript(schema)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def ensure_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        asset_class = str(asset.get("asset_class", "")).strip()
        subclass = str(asset.get("subclass", "")).strip()
        if asset_class not in ASSET_CLASSES:
            raise ValueError("asset_class must be stock or fund")
        if subclass not in ASSET_SUBCLASSES:
            raise ValueError("Unsupported asset subclass")
        if asset_class == "stock" and subclass not in {"cn", "hk", "us"}:
            raise ValueError("Stock subclass must be cn, hk or us")
        if asset_class == "fund" and subclass not in {"exchange_traded", "otc"}:
            raise ValueError("Fund subclass must be exchange_traded or otc")

        symbol = str(asset.get("symbol", "")).strip().upper()
        provider_symbol = str(asset.get("provider_symbol") or symbol).strip().upper()
        name = str(asset.get("name") or symbol).strip()
        market = str(asset.get("market", "")).strip().upper()
        if not symbol or not provider_symbol or not name or not market:
            raise ValueError("symbol, name and market are required")

        now = utc_now_iso()
        values = (
            symbol,
            provider_symbol,
            name,
            asset_class,
            subclass,
            market,
            str(asset.get("exchange") or "").strip().upper(),
            str(asset.get("currency") or "CNY").strip().upper(),
            str(asset.get("timezone") or "Asia/Shanghai").strip(),
            str(asset.get("source") or "manual").strip(),
            now,
            now,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO assets (
                    symbol, provider_symbol, name, asset_class, subclass, market,
                    exchange, currency, timezone, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_class, market, provider_symbol) DO UPDATE SET
                    symbol=excluded.symbol,
                    name=excluded.name,
                    subclass=excluded.subclass,
                    exchange=excluded.exchange,
                    currency=excluded.currency,
                    timezone=excluded.timezone,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                values,
            )
            row = connection.execute(
                """SELECT * FROM assets
                   WHERE asset_class=? AND market=? AND provider_symbol=?""",
                (asset_class, market, provider_symbol),
            ).fetchone()
        return dict(row)

    def get_asset(self, asset_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        return self._row(row)

    def list_local_assets(
        self,
        query: str = "",
        asset_class: str | None = None,
        subclass: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if query:
            clauses.append("(symbol LIKE ? OR name LIKE ? OR provider_symbol LIKE ?)")
            needle = f"%{query}%"
            params.extend([needle, needle, needle])
        if asset_class:
            clauses.append("asset_class=?")
            params.append(asset_class)
        if subclass:
            clauses.append("subclass=?")
            params.append(subclass)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM assets {where} ORDER BY name LIMIT 50", params
            ).fetchall()
        return [dict(row) for row in rows]

    def add_watchlist(self, asset_id: int, owner_id: str = DEFAULT_OWNER, group_name: str = "默认") -> None:
        if not self.get_asset(asset_id):
            raise ValueError("Asset not found")
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO watchlists(owner_id, asset_id, group_name, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(owner_id, asset_id) DO UPDATE SET group_name=excluded.group_name""",
                (owner_id, asset_id, group_name.strip() or "默认", utc_now_iso()),
            )

    def remove_watchlist(self, asset_id: int, owner_id: str = DEFAULT_OWNER) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM watchlists WHERE owner_id=? AND asset_id=?",
                (owner_id, asset_id),
            )

    def list_watchlist(self, owner_id: str = DEFAULT_OWNER) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.*, w.group_name, w.created_at AS watchlisted_at,
                       q.price, q.previous_close, q.change_value, q.change_percent,
                       q.quote_time, q.received_at, q.is_delayed, q.source AS quote_source
                FROM watchlists w
                JOIN assets a ON a.id=w.asset_id
                LEFT JOIN latest_quotes q ON q.asset_id=a.id
                WHERE w.owner_id=?
                ORDER BY w.created_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def tracked_asset_ids(self, owner_id: str = DEFAULT_OWNER) -> list[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT asset_id FROM watchlists WHERE owner_id=?",
                (owner_id,),
            ).fetchall()
        asset_ids = {int(row[0]) for row in rows}
        asset_ids.update(int(position["id"]) for position in self.calculate_positions(owner_id))
        return sorted(asset_ids)

    def upsert_quote(self, asset_id: int, quote: dict[str, Any]) -> None:
        price = float(quote["price"])
        previous_close = quote.get("previous_close")
        previous_close = float(previous_close) if previous_close not in (None, "") else None
        change_value = price - previous_close if previous_close else None
        change_percent = change_value / previous_close * 100 if previous_close else None
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO latest_quotes(
                    asset_id, price, previous_close, change_value, change_percent,
                    currency, quote_time, received_at, source, is_delayed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    price=excluded.price,
                    previous_close=excluded.previous_close,
                    change_value=excluded.change_value,
                    change_percent=excluded.change_percent,
                    currency=excluded.currency,
                    quote_time=excluded.quote_time,
                    received_at=excluded.received_at,
                    source=excluded.source,
                    is_delayed=excluded.is_delayed
                """,
                (
                    asset_id,
                    price,
                    previous_close,
                    change_value,
                    change_percent,
                    quote.get("currency") or "CNY",
                    quote.get("quote_time") or utc_now_iso(),
                    utc_now_iso(),
                    quote.get("source") or "unknown",
                    int(bool(quote.get("is_delayed", False))),
                ),
            )

    def get_quote(self, asset_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM latest_quotes WHERE asset_id=?", (asset_id,)
            ).fetchone()
        return self._row(row)

    def upsert_daily_bars(self, asset_id: int, bars: Iterable[dict[str, Any]]) -> int:
        records = []
        for bar in bars:
            if bar.get("close") is None or not bar.get("date"):
                continue
            records.append(
                (
                    asset_id,
                    str(bar["date"]),
                    bar.get("open"),
                    bar.get("high"),
                    bar.get("low"),
                    float(bar["close"]),
                    bar.get("volume"),
                    bar.get("source") or "unknown",
                )
            )
        if not records:
            return 0
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO daily_bars(asset_id, bar_date, open, high, low, close, volume, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, bar_date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume, source=excluded.source
                """,
                records,
            )
        return len(records)

    def get_daily_bars(self, asset_id: int, limit: int = 520) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT * FROM daily_bars WHERE asset_id=?
                    ORDER BY bar_date DESC LIMIT ?
                ) ORDER BY bar_date
                """,
                (asset_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_predictions(
        self,
        asset_id: int,
        quote_time: str,
        base_price: float,
        predictions: Iterable[dict[str, Any]],
        model_version: str,
    ) -> None:
        generated_at = utc_now_iso()
        records = []
        for item in predictions:
            records.append(
                (
                    asset_id,
                    generated_at,
                    quote_time,
                    base_price,
                    int(item["horizon_days"]),
                    float(item["probability_up"]),
                    float(item["probability_flat"]),
                    float(item["probability_down"]),
                    item.get("expected_low"),
                    item.get("expected_high"),
                    item.get("confidence") or "low",
                    model_version,
                )
            )
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO predictions(
                    asset_id, generated_at, quote_time, base_price, horizon_days,
                    probability_up, probability_flat, probability_down,
                    expected_low, expected_high, confidence, model_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, quote_time, horizon_days, model_version) DO UPDATE SET
                    generated_at=excluded.generated_at,
                    base_price=excluded.base_price,
                    probability_up=excluded.probability_up,
                    probability_flat=excluded.probability_flat,
                    probability_down=excluded.probability_down,
                    expected_low=excluded.expected_low,
                    expected_high=excluded.expected_high,
                    confidence=excluded.confidence
                """,
                records,
            )

    def latest_predictions(self, asset_id: int) -> list[dict[str, Any]]:
        quote = self.get_quote(asset_id)
        asset = self.get_asset(asset_id)
        is_otc_fund = bool(asset and asset.get("subclass") == "otc")
        with self.connect() as connection:
            rows = []
            if quote:
                candidates = connection.execute(
                    """SELECT * FROM predictions
                       WHERE asset_id=? AND quote_time=?
                       ORDER BY id DESC""",
                    (asset_id, quote["quote_time"]),
                ).fetchall()
                quote_price = float(quote["price"])
                tolerance = max(1e-8, abs(quote_price) * 1e-8)
                latest_by_horizon = {}
                for row in candidates:
                    horizon = int(row["horizon_days"])
                    if abs(float(row["base_price"]) - quote_price) <= tolerance:
                        latest_by_horizon.setdefault(horizon, row)
                rows = [latest_by_horizon[key] for key in sorted(latest_by_horizon)]
            if not rows:
                rows = connection.execute(
                    """
                    SELECT p.* FROM predictions p
                    JOIN (
                        SELECT horizon_days, MAX(id) AS max_id
                        FROM predictions WHERE asset_id=? GROUP BY horizon_days
                    ) latest ON latest.max_id=p.id
                    ORDER BY p.horizon_days
                    """,
                    (asset_id,),
                ).fetchall()
        output = [dict(row) for row in rows]
        if is_otc_fund:
            # Normalize legacy rows so the public contract is binary
            # even before the next background refresh writes the new model.
            for item in output:
                directional_total = float(item["probability_up"]) + float(item["probability_down"])
                if directional_total > 0:
                    item["probability_up"] = float(item["probability_up"]) / directional_total
                    item["probability_down"] = float(item["probability_down"]) / directional_total
                else:
                    item["probability_up"] = item["probability_down"] = 0.5
                item["probability_flat"] = 0.0
        return output

    def _quantity_for_asset(self, asset_id: int, owner_id: str) -> float:
        quantity = 0.0
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT transaction_type, quantity FROM transactions
                   WHERE owner_id=? AND asset_id=? ORDER BY occurred_at, created_at""",
                (owner_id, asset_id),
            ).fetchall()
        for row in rows:
            kind = row["transaction_type"]
            amount = float(row["quantity"] or 0)
            if kind in {"buy", "subscribe"}:
                quantity += amount
            elif kind in {"sell", "redeem"}:
                quantity -= amount
            elif kind == "split" and amount > 0:
                quantity *= amount
        return quantity

    def add_transaction(self, payload: dict[str, Any], owner_id: str = DEFAULT_OWNER) -> dict[str, Any]:
        asset_id = int(payload.get("asset_id", 0))
        asset = self.get_asset(asset_id)
        if not asset:
            raise ValueError("Asset not found")
        kind = str(payload.get("transaction_type", "")).strip().lower()
        if kind not in TRANSACTION_TYPES:
            raise ValueError("Unsupported transaction type")

        quantity = float(payload.get("quantity") or 0)
        price = float(payload.get("price") or 0)
        fees = float(payload.get("fees") or 0)
        taxes = float(payload.get("taxes") or 0)
        cash_amount = float(payload.get("cash_amount") or 0)
        fx_rate = float(payload.get("fx_rate") or 1)
        if min(quantity, price, fees, taxes, cash_amount) < 0 or fx_rate <= 0:
            raise ValueError("Transaction numbers cannot be negative")
        if kind in {"buy", "sell", "subscribe", "redeem"} and (quantity <= 0 or price <= 0):
            raise ValueError("Quantity and price must be positive")
        if kind == "dividend" and cash_amount <= 0:
            raise ValueError("Dividend cash amount must be positive")
        if kind == "split" and quantity <= 0:
            raise ValueError("Split ratio must be positive")
        if kind in {"sell", "redeem"}:
            held = self._quantity_for_asset(asset_id, owner_id)
            if quantity > held + 1e-9:
                raise ValueError("Cannot sell more than the current holding")

        transaction_id = str(uuid.uuid4())
        occurred_at = str(payload.get("occurred_at") or utc_now_iso()).strip()
        try:
            datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("occurred_at must be an ISO date and time") from error
        created_at = utc_now_iso()
        values = (
            transaction_id,
            owner_id,
            asset_id,
            kind,
            occurred_at,
            quantity,
            price,
            fees,
            taxes,
            cash_amount,
            str(payload.get("currency") or asset["currency"]).upper(),
            fx_rate,
            str(payload.get("note") or "").strip(),
            created_at,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO transactions(
                    id, owner_id, asset_id, transaction_type, occurred_at,
                    quantity, price, fees, taxes, cash_amount, currency,
                    fx_rate, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            if kind in {"buy", "subscribe"}:
                connection.execute(
                    """INSERT INTO watchlists(owner_id, asset_id, group_name, created_at)
                       VALUES (?, ?, '默认', ?)
                       ON CONFLICT(owner_id, asset_id) DO NOTHING""",
                    (owner_id, asset_id, created_at),
                )
        return self.get_transaction(transaction_id)  # type: ignore[return-value]

    def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM transactions WHERE id=?", (transaction_id,)
            ).fetchone()
        return self._row(row)

    def list_transactions(self, owner_id: str = DEFAULT_OWNER, asset_id: int | None = None) -> list[dict[str, Any]]:
        params: list[Any] = [owner_id]
        asset_filter = ""
        if asset_id is not None:
            asset_filter = "AND t.asset_id=?"
            params.append(asset_id)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT t.*, a.symbol, a.name, a.asset_class, a.subclass, a.market
                FROM transactions t JOIN assets a ON a.id=t.asset_id
                WHERE t.owner_id=? {asset_filter}
                ORDER BY t.occurred_at DESC, t.created_at DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def calculate_positions(self, owner_id: str = DEFAULT_OWNER, include_closed: bool = False) -> list[dict[str, Any]]:
        transactions = list(reversed(self.list_transactions(owner_id)))
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for transaction in transactions:
            grouped[int(transaction["asset_id"])].append(transaction)

        positions = []
        for asset_id, rows in grouped.items():
            quantity = 0.0
            remaining_cost = 0.0
            realized = 0.0
            dividends = 0.0
            total_fees = 0.0
            gross_invested = 0.0
            for row in rows:
                kind = row["transaction_type"]
                amount = float(row["quantity"] or 0)
                price = float(row["price"] or 0)
                fees = float(row["fees"] or 0) + float(row["taxes"] or 0)
                total_fees += fees
                if kind in {"buy", "subscribe"}:
                    purchase_cost = amount * price + fees
                    quantity += amount
                    remaining_cost += purchase_cost
                    gross_invested += purchase_cost
                elif kind in {"sell", "redeem"} and quantity > 0:
                    sold = min(amount, quantity)
                    average_cost = remaining_cost / quantity if quantity else 0
                    allocated_cost = average_cost * sold
                    proceeds = sold * price - fees
                    realized += proceeds - allocated_cost
                    quantity -= sold
                    remaining_cost -= allocated_cost
                    if quantity < 1e-9:
                        quantity = 0.0
                        remaining_cost = 0.0
                elif kind == "dividend":
                    dividends += float(row["cash_amount"] or 0) - fees
                elif kind == "fee":
                    realized -= float(row["cash_amount"] or 0) + fees
                elif kind == "split" and amount > 0:
                    quantity *= amount

            if quantity <= 1e-9 and not include_closed:
                continue
            asset = self.get_asset(asset_id)
            if not asset:
                continue
            quote = self.get_quote(asset_id)
            current_price = float(quote["price"]) if quote else None
            market_value = quantity * current_price if current_price is not None else None
            unrealized = market_value - remaining_cost if market_value is not None else None
            total_profit = realized + dividends + (unrealized or 0)
            positions.append(
                {
                    **asset,
                    "quantity": quantity,
                    "average_cost": remaining_cost / quantity if quantity else 0,
                    "remaining_cost": remaining_cost,
                    "current_price": current_price,
                    "market_value": market_value,
                    "realized_profit": realized,
                    "unrealized_profit": unrealized,
                    "dividends": dividends,
                    "fees": total_fees,
                    "total_profit": total_profit,
                    "return_percent": total_profit / gross_invested * 100 if gross_invested else None,
                    "quote_time": quote.get("quote_time") if quote else None,
                    "change_percent": quote.get("change_percent") if quote else None,
                }
            )
        return sorted(positions, key=lambda item: item["name"])

    def portfolio_summary(self, owner_id: str = DEFAULT_OWNER) -> dict[str, Any]:
        positions = self.calculate_positions(owner_id)
        by_currency: dict[str, dict[str, float]] = defaultdict(
            lambda: {"market_value": 0.0, "remaining_cost": 0.0, "total_profit": 0.0}
        )
        for position in positions:
            currency = position["currency"]
            if position["market_value"] is not None:
                by_currency[currency]["market_value"] += position["market_value"]
            by_currency[currency]["remaining_cost"] += position["remaining_cost"]
            by_currency[currency]["total_profit"] += position["total_profit"]
        return {"position_count": len(positions), "by_currency": dict(by_currency)}
