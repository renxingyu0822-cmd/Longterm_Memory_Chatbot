"""Pluggable market-data providers for the local investment workspace.

Yahoo Finance is used as a best-effort, personal-use prototype source. The
provider is isolated so a licensed feed can replace it before public release.
A clearly labelled deterministic demo fallback keeps the local UI usable when
the network or a symbol is unavailable.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote as url_quote
from zoneinfo import ZoneInfo

import requests


class MarketDataError(RuntimeError):
    pass


SHANGHAI_TZ = timezone(timedelta(hours=8))


CATALOG: list[dict[str, Any]] = [
    {"symbol": "600519", "provider_symbol": "600519.SS", "name": "贵州茅台", "asset_class": "stock", "subclass": "cn", "market": "CN", "exchange": "SSE", "currency": "CNY", "timezone": "Asia/Shanghai", "base_price": 1500.0},
    {"symbol": "000001", "provider_symbol": "000001.SZ", "name": "平安银行", "asset_class": "stock", "subclass": "cn", "market": "CN", "exchange": "SZSE", "currency": "CNY", "timezone": "Asia/Shanghai", "base_price": 12.0},
    {"symbol": "0700", "provider_symbol": "0700.HK", "name": "腾讯控股", "asset_class": "stock", "subclass": "hk", "market": "HK", "exchange": "HKEX", "currency": "HKD", "timezone": "Asia/Hong_Kong", "base_price": 500.0},
    {"symbol": "9988", "provider_symbol": "9988.HK", "name": "阿里巴巴-W", "asset_class": "stock", "subclass": "hk", "market": "HK", "exchange": "HKEX", "currency": "HKD", "timezone": "Asia/Hong_Kong", "base_price": 120.0},
    {"symbol": "AAPL", "provider_symbol": "AAPL", "name": "Apple", "asset_class": "stock", "subclass": "us", "market": "US", "exchange": "NASDAQ", "currency": "USD", "timezone": "America/New_York", "base_price": 220.0},
    {"symbol": "MSFT", "provider_symbol": "MSFT", "name": "Microsoft", "asset_class": "stock", "subclass": "us", "market": "US", "exchange": "NASDAQ", "currency": "USD", "timezone": "America/New_York", "base_price": 500.0},
    {"symbol": "NVDA", "provider_symbol": "NVDA", "name": "NVIDIA", "asset_class": "stock", "subclass": "us", "market": "US", "exchange": "NASDAQ", "currency": "USD", "timezone": "America/New_York", "base_price": 170.0},
    {"symbol": "510300", "provider_symbol": "510300.SS", "name": "沪深300ETF", "asset_class": "fund", "subclass": "exchange_traded", "market": "CN", "exchange": "SSE", "currency": "CNY", "timezone": "Asia/Shanghai", "base_price": 4.2},
    {"symbol": "159915", "provider_symbol": "159915.SZ", "name": "创业板ETF", "asset_class": "fund", "subclass": "exchange_traded", "market": "CN", "exchange": "SZSE", "currency": "CNY", "timezone": "Asia/Shanghai", "base_price": 2.1},
    {"symbol": "SPY", "provider_symbol": "SPY", "name": "SPDR S&P 500 ETF", "asset_class": "fund", "subclass": "exchange_traded", "market": "US", "exchange": "NYSE", "currency": "USD", "timezone": "America/New_York", "base_price": 650.0},
    {"symbol": "110022", "provider_symbol": "110022.OF", "name": "易方达消费行业股票", "asset_class": "fund", "subclass": "otc", "market": "CN", "exchange": "OTC", "currency": "CNY", "timezone": "Asia/Shanghai", "base_price": 3.6},
    {"symbol": "005827", "provider_symbol": "005827.OF", "name": "易方达蓝筹精选混合", "asset_class": "fund", "subclass": "otc", "market": "CN", "exchange": "OTC", "currency": "CNY", "timezone": "Asia/Shanghai", "base_price": 2.0},
]


def _matches(item: dict[str, Any], query: str, asset_class: str | None, subclass: str | None) -> bool:
    needle = query.casefold().strip()
    if asset_class and item["asset_class"] != asset_class:
        return False
    if subclass and item["subclass"] != subclass:
        return False
    return not needle or needle in item["symbol"].casefold() or needle in item["name"].casefold()


def _catalog_item(provider_symbol: str) -> dict[str, Any] | None:
    normalized = provider_symbol.upper()
    return next((dict(item) for item in CATALOG if item["provider_symbol"].upper() == normalized), None)


class DemoMarketDataProvider:
    name = "demo"

    def search(self, query: str, asset_class: str | None = None, subclass: str | None = None) -> list[dict[str, Any]]:
        return [
            {**item, "source": "demo"}
            for item in CATALOG
            if _matches(item, query, asset_class, subclass)
        ][:20]

    @staticmethod
    def _seed(provider_symbol: str) -> int:
        return sum((index + 1) * ord(char) for index, char in enumerate(provider_symbol))

    def quote(self, asset: dict[str, Any]) -> dict[str, Any]:
        seed = self._seed(asset["provider_symbol"])
        catalog_item = _catalog_item(asset["provider_symbol"])
        if asset.get("subclass") == "otc" and not catalog_item:
            raise MarketDataError(
                "No demo NAV is available for this OTC fund; keeping the last official NAV"
            )
        catalog = catalog_item or {}
        base = float(catalog.get("base_price") or 100.0)
        if asset.get("subclass") == "otc":
            phase = datetime.now().toordinal() / 17 + seed
            price = base * (1 + 0.035 * math.sin(phase))
            quote_time = datetime.now(SHANGHAI_TZ).replace(
                hour=20, minute=0, second=0, microsecond=0
            )
            if quote_time > datetime.now(SHANGHAI_TZ):
                quote_time -= timedelta(days=1)
            is_delayed = True
        else:
            phase = time.time() / 240 + seed
            price = base * (1 + 0.018 * math.sin(phase))
            quote_time = datetime.now(timezone.utc)
            is_delayed = False
        previous_close = base * (1 + 0.015 * math.sin(phase - 0.8))
        return {
            "price": round(price, 4),
            "previous_close": round(previous_close, 4),
            "currency": asset.get("currency") or catalog.get("currency") or "CNY",
            "quote_time": quote_time.isoformat(timespec="seconds"),
            "source": "demo",
            "is_delayed": is_delayed,
        }

    def history(self, asset: dict[str, Any], days: int = 520) -> list[dict[str, Any]]:
        seed = self._seed(asset["provider_symbol"])
        randomizer = random.Random(seed)
        catalog_item = _catalog_item(asset["provider_symbol"])
        if asset.get("subclass") == "otc" and not catalog_item:
            raise MarketDataError(
                "No demo NAV history is available for this OTC fund; keeping official history"
            )
        catalog = catalog_item or {}
        base = float(catalog.get("base_price") or 100.0)
        volatility = 0.008 if asset.get("subclass") == "otc" else 0.016
        price = base * 0.76
        trading_dates = []
        current_date = datetime.now().date()
        while len(trading_dates) < days:
            if current_date.weekday() < 5:
                trading_dates.append(current_date)
            current_date -= timedelta(days=1)
        trading_dates.reverse()
        bars = []
        for current_date in trading_dates:
            drift = 0.00045 + 0.0003 * math.sin(len(bars) / 31 + seed)
            price = max(0.01, price * (1 + drift + randomizer.gauss(0, volatility)))
            open_price = price * (1 + randomizer.gauss(0, volatility / 3))
            high = max(open_price, price) * (1 + abs(randomizer.gauss(0, volatility / 2)))
            low = min(open_price, price) * (1 - abs(randomizer.gauss(0, volatility / 2)))
            bars.append(
                {
                    "date": current_date.isoformat(),
                    "open": round(open_price, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(price, 4),
                    "volume": round(randomizer.uniform(1_000_000, 50_000_000)),
                    "source": "demo",
                }
            )
        return bars


class YahooFinanceProvider:
    name = "yahoo"
    base_url = "https://query1.finance.yahoo.com"

    def __init__(self, timeout: float = 7.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 ThumperLocalInvestmentWorkspace/1.0",
                "Accept": "application/json",
            }
        )

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}{path}", params=params, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            raise MarketDataError(f"Yahoo market data unavailable: {error}") from error

    @staticmethod
    def _profile(item: dict[str, Any]) -> dict[str, Any] | None:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            return None
        quote_type = str(item.get("quoteType") or "").upper()
        exchange = str(item.get("exchange") or item.get("exchDisp") or "").upper()
        is_fund = quote_type in {"ETF", "MUTUALFUND"}
        if quote_type == "MUTUALFUND":
            asset_class, subclass, market = "fund", "otc", "US"
        elif is_fund:
            asset_class, subclass = "fund", "exchange_traded"
            market = "CN" if symbol.endswith((".SS", ".SZ")) else "HK" if symbol.endswith(".HK") else "US"
        elif symbol.endswith((".SS", ".SZ")):
            asset_class, subclass, market = "stock", "cn", "CN"
        elif symbol.endswith(".HK"):
            asset_class, subclass, market = "stock", "hk", "HK"
        else:
            asset_class, subclass, market = "stock", "us", "US"
        currency = "CNY" if market == "CN" else "HKD" if market == "HK" else "USD"
        timezone_name = "Asia/Shanghai" if market == "CN" else "Asia/Hong_Kong" if market == "HK" else "America/New_York"
        display_symbol = symbol.split(".")[0] if market in {"CN", "HK"} else symbol
        return {
            "symbol": display_symbol,
            "provider_symbol": symbol,
            "name": item.get("longname") or item.get("shortname") or symbol,
            "asset_class": asset_class,
            "subclass": subclass,
            "market": market,
            "exchange": exchange,
            "currency": currency,
            "timezone": timezone_name,
            "source": "yahoo",
        }

    def search(self, query: str, asset_class: str | None = None, subclass: str | None = None) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        payload = self._get_json(
            "/v1/finance/search",
            {"q": query, "quotesCount": 20, "newsCount": 0, "listsCount": 0},
        )
        results = []
        for item in payload.get("quotes", []):
            profile = self._profile(item)
            if not profile or profile["asset_class"] not in {"stock", "fund"}:
                continue
            if asset_class and profile["asset_class"] != asset_class:
                continue
            if subclass and profile["subclass"] != subclass:
                continue
            results.append(profile)
        return results

    def _chart(self, provider_symbol: str, range_value: str, interval: str) -> dict[str, Any]:
        payload = self._get_json(
            f"/v8/finance/chart/{url_quote(provider_symbol, safe='')}",
            {"range": range_value, "interval": interval, "events": "div,splits"},
        )
        chart = payload.get("chart", {})
        if chart.get("error"):
            raise MarketDataError(str(chart["error"]))
        results = chart.get("result") or []
        if not results:
            raise MarketDataError("No market data returned for symbol")
        return results[0]

    def quote(self, asset: dict[str, Any]) -> dict[str, Any]:
        result = self._chart(asset["provider_symbol"], "1d", "1m")
        meta = result.get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            price = next((value for value in reversed(closes) if value is not None), None)
        if price is None:
            raise MarketDataError("Quote has no price")
        timestamp = meta.get("regularMarketTime")
        quote_time = datetime.fromtimestamp(timestamp, timezone.utc) if timestamp else datetime.now(timezone.utc)
        return {
            "price": float(price),
            "previous_close": meta.get("chartPreviousClose") or meta.get("previousClose"),
            "currency": meta.get("currency") or asset.get("currency") or "CNY",
            "quote_time": quote_time.isoformat(timespec="seconds"),
            "source": "yahoo",
            "is_delayed": True,
        }

    def history(self, asset: dict[str, Any], days: int = 520) -> list[dict[str, Any]]:
        result = self._chart(asset["provider_symbol"], "2y", "1d")
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quote_rows = (indicators.get("quote") or [{}])[0]
        adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
        timezone_name = (result.get("meta") or {}).get("exchangeTimezoneName") or asset.get("timezone") or "UTC"
        try:
            exchange_zone = ZoneInfo(timezone_name)
        except Exception:
            exchange_zone = timezone.utc
        bars = []
        for index, timestamp in enumerate(timestamps):
            raw_close = (quote_rows.get("close") or [None] * len(timestamps))[index]
            close = adjusted[index] if index < len(adjusted) and adjusted[index] is not None else raw_close
            if close is None:
                continue
            def value(field: str):
                values = quote_rows.get(field) or []
                return values[index] if index < len(values) else None
            bars.append(
                {
                    "date": datetime.fromtimestamp(timestamp, exchange_zone).date().isoformat(),
                    "open": value("open"),
                    "high": value("high"),
                    "low": value("low"),
                    "close": float(close),
                    "volume": value("volume"),
                    "source": "yahoo",
                }
            )
        return bars[-days:]


class EastmoneyFundProvider:
    """Search Chinese OTC funds and load their published NAV history."""

    name = "eastmoney"
    search_url = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
    trend_url = "https://fund.eastmoney.com/pingzhongdata/{code}.js"

    def __init__(self, timeout: float = 7.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 ThumperLocalInvestmentWorkspace/1.0",
                "Accept": "application/json",
                "Referer": "https://fund.eastmoney.com/",
            }
        )

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt == 0:
                    time.sleep(0.25)
        raise MarketDataError(f"Eastmoney fund data unavailable: {last_error}") from last_error

    def _get_text(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            except requests.RequestException as error:
                last_error = error
                if attempt == 0:
                    time.sleep(0.25)
        raise MarketDataError(f"Eastmoney fund history unavailable: {last_error}") from last_error

    @staticmethod
    def _profile(item: dict[str, Any]) -> dict[str, Any] | None:
        code = str(item.get("CODE") or item.get("_id") or "").strip()
        category = str(item.get("CATEGORYDESC") or "")
        if not (len(code) == 6 and code.isdigit()) or "基金" not in category:
            return None
        base_info = item.get("FundBaseInfo") or {}
        return {
            "symbol": code,
            "provider_symbol": f"{code}.OF",
            "name": base_info.get("SHORTNAME") or item.get("NAME") or code,
            "asset_class": "fund",
            "subclass": "otc",
            "market": "CN",
            "exchange": "OTC",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "source": "eastmoney",
        }

    def _search_items(self, query: str) -> list[dict[str, Any]]:
        payload = self._get_json(self.search_url, {"m": 1, "key": query.strip()})
        if payload.get("ErrCode") not in {None, 0}:
            raise MarketDataError(str(payload.get("ErrMsg") or "Fund search failed"))
        return payload.get("Datas") or []

    def search(
        self,
        query: str,
        asset_class: str | None = None,
        subclass: str | None = None,
    ) -> list[dict[str, Any]]:
        if not query.strip() or asset_class not in {None, "fund"} or subclass not in {None, "otc"}:
            return []
        results = []
        for item in self._search_items(query):
            profile = self._profile(item)
            if profile:
                results.append(profile)
        return results[:20]

    @staticmethod
    def _fund_code(asset: dict[str, Any]) -> str:
        return str(asset.get("provider_symbol") or asset.get("symbol") or "").split(".")[0]

    def quote(self, asset: dict[str, Any]) -> dict[str, Any]:
        code = self._fund_code(asset)
        exact = next(
            (
                item
                for item in self._search_items(code)
                if str(item.get("CODE") or item.get("_id") or "") == code
            ),
            None,
        )
        base_info = (exact or {}).get("FundBaseInfo") or {}
        nav = base_info.get("DWJZ")
        nav_date = str(base_info.get("FSRQ") or "")
        if nav is None or not nav_date:
            raise MarketDataError("The fund has no published NAV yet")
        quote_time = datetime.fromisoformat(nav_date).replace(
            hour=20,
            tzinfo=SHANGHAI_TZ,
        )
        return {
            "price": float(nav),
            "previous_close": None,
            "currency": "CNY",
            "quote_time": quote_time.isoformat(timespec="seconds"),
            "source": "eastmoney",
            "is_delayed": True,
        }

    def history(self, asset: dict[str, Any], days: int = 520) -> list[dict[str, Any]]:
        code = self._fund_code(asset)
        text = self._get_text(self.trend_url.format(code=code))
        match = re.search(r"var Data_netWorthTrend\s*=\s*(\[.*?\]);", text, re.DOTALL)
        if not match:
            raise MarketDataError("Fund history has an unsupported response format")
        try:
            rows = json.loads(match.group(1))
        except ValueError as error:
            raise MarketDataError(f"Fund history could not be decoded: {error}") from error
        bars = []
        for row in rows:
            nav = row.get("y")
            timestamp = row.get("x")
            if nav in {None, ""} or timestamp is None:
                continue
            price = float(nav)
            bars.append(
                {
                    "date": datetime.fromtimestamp(float(timestamp) / 1000, SHANGHAI_TZ).date().isoformat(),
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": None,
                    "source": "eastmoney",
                }
            )
        bars.sort(key=lambda item: item["date"])
        return bars[-days:]


class HybridMarketDataProvider:
    """Use live Yahoo data when available and a labelled demo fallback otherwise."""

    name = "hybrid"

    def __init__(self):
        self.yahoo = YahooFinanceProvider()
        self.eastmoney = EastmoneyFundProvider()
        self.demo = DemoMarketDataProvider()
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _cached(self, key: tuple[str, str], ttl: int, loader):
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < ttl:
                return cached[1]
        value = loader()
        with self._lock:
            self._cache[key] = (now, value)
        return value

    def search(self, query: str, asset_class: str | None = None, subclass: str | None = None) -> list[dict[str, Any]]:
        local = self.demo.search(query, asset_class, subclass)
        if os.getenv("MARKET_DATA_PROVIDER", "hybrid").lower() == "demo":
            return local
        fund_results = []
        if asset_class in {None, "fund"} and subclass in {None, "otc"}:
            try:
                fund_results = self._cached(
                    ("fund-search", f"{query}:{asset_class}:{subclass}"),
                    300,
                    lambda: self.eastmoney.search(query, asset_class, subclass),
                )
            except MarketDataError:
                fund_results = []
        yahoo_results = []
        if subclass != "otc":
            try:
                yahoo_results = self._cached(
                    ("search", f"{query}:{asset_class}:{subclass}"),
                    300,
                    lambda: self.yahoo.search(query, asset_class, subclass),
                )
            except MarketDataError:
                yahoo_results = []
        merged: dict[str, dict[str, Any]] = {
            item["provider_symbol"]: item for item in [*fund_results, *yahoo_results]
        }
        for item in local:
            merged.setdefault(item["provider_symbol"], item)
        return list(merged.values())[:20]

    def quote(self, asset: dict[str, Any]) -> dict[str, Any]:
        use_demo = os.getenv("MARKET_DATA_PROVIDER", "hybrid").lower() == "demo"
        if not use_demo and asset.get("subclass") == "otc":
            try:
                return self._cached(
                    ("fund-quote", asset["provider_symbol"]),
                    int(os.getenv("MARKET_QUOTE_CACHE_SECONDS", "30")),
                    lambda: self.eastmoney.quote(asset),
                )
            except MarketDataError:
                return self.demo.quote(asset)
        if not use_demo:
            try:
                return self._cached(
                    ("quote", asset["provider_symbol"]),
                    int(os.getenv("MARKET_QUOTE_CACHE_SECONDS", "30")),
                    lambda: self.yahoo.quote(asset),
                )
            except MarketDataError:
                pass
        return self.demo.quote(asset)

    def history(self, asset: dict[str, Any], days: int = 520) -> list[dict[str, Any]]:
        use_demo = os.getenv("MARKET_DATA_PROVIDER", "hybrid").lower() == "demo"
        if not use_demo and asset.get("subclass") == "otc":
            try:
                return self._cached(
                    ("fund-history", asset["provider_symbol"]),
                    3600,
                    lambda: self.eastmoney.history(asset, days),
                )
            except MarketDataError:
                return self.demo.history(asset, days)
        if not use_demo:
            try:
                return self._cached(
                    ("history", asset["provider_symbol"]),
                    3600,
                    lambda: self.yahoo.history(asset, days),
                )
            except MarketDataError:
                pass
        return self.demo.history(asset, days)


provider = HybridMarketDataProvider()
