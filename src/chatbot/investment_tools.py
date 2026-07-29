"""Investment data tools exposed to the LLM via OpenAI function calling.

Calls the standalone investment service (investment_app.py) over HTTP.
Set INVESTMENT_SERVICE_URL to override the default localhost:8081.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

_BASE = os.getenv("INVESTMENT_SERVICE_URL", "http://127.0.0.1:8081")
_TIMEOUT = 5  # seconds


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": (
                "Returns the user's current portfolio: held positions with cost basis, current "
                "price, and P&L; watchlist-only items; and an overall portfolio summary. "
                "Call this when the user asks about their holdings, portfolio value, or what "
                "they are currently watching."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_asset",
            "description": (
                "Returns the current quote and short-term price-direction predictions "
                "(1-, 3-, 5-, and 20-trading-day horizons) for a specific stock or fund. "
                "Call this when the user asks about a specific asset's current price, "
                "outlook, or model prediction."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": (
                            "Stock ticker or fund code, e.g. '000001', '513100', 'AAPL'."
                        ),
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_assets",
            "description": (
                "Search for stocks or funds by name or symbol. Use this to look up what "
                "a ticker or fund code refers to, or to find an asset before fetching its detail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — a name fragment or ticker/fund code.",
                    },
                    "asset_class": {
                        "type": "string",
                        "enum": ["stock", "fund"],
                        "description": "Optional filter by asset class.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def execute(name: str, arguments: dict[str, Any], svc: Any = None) -> str:
    """Execute a named tool call via HTTP and return a JSON string result."""
    try:
        if name == "get_portfolio":
            r = requests.get(f"{_BASE}/api/portfolio", timeout=_TIMEOUT)
            data = r.json()
            return json.dumps(
                {
                    "positions": data.get("positions", []),
                    "watchlist_only": data.get("watchlist_only", []),
                    "summary": data.get("summary", {}),
                },
                ensure_ascii=False,
            )

        if name == "get_asset":
            symbol = str(arguments.get("symbol", "")).strip()
            if not symbol:
                return json.dumps({"error": "symbol is required"})
            # Search first to resolve symbol → asset_id
            r = requests.get(f"{_BASE}/api/market/search", params={"q": symbol}, timeout=_TIMEOUT)
            results = r.json().get("results", [])
            if not results:
                return json.dumps({"error": f"Asset not found: {symbol}"})
            asset_id = results[0]["id"]
            r = requests.get(f"{_BASE}/api/market/assets/{asset_id}", timeout=_TIMEOUT)
            detail = r.json()
            return json.dumps(
                {
                    "name": detail.get("name"),
                    "symbol": detail.get("symbol"),
                    "subclass": detail.get("subclass"),
                    "quote": detail.get("quote"),
                    "predictions": detail.get("predictions"),
                    "risk": detail.get("risk"),
                },
                ensure_ascii=False,
                default=str,
            )

        if name == "search_assets":
            query = str(arguments.get("query", "")).strip()
            params: dict[str, str] = {"q": query}
            if arguments.get("asset_class"):
                params["asset_class"] = arguments["asset_class"]
            r = requests.get(f"{_BASE}/api/market/search", params=params, timeout=_TIMEOUT)
            results = r.json().get("results", [])
            return json.dumps(results[:5], ensure_ascii=False, default=str)

        return json.dumps({"error": f"Unknown tool: {name}"})

    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "Investment service is not running (port 8081)"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def habit_summaries(svc: Any = None) -> list[str]:
    """Return active investment habit summaries for passive system-prompt injection."""
    try:
        r = requests.get(f"{_BASE}/api/habits", timeout=2)
        return [
            str(h["summary"])
            for h in r.json().get("habits", [])
            if h.get("summary")
        ]
    except Exception:
        return []


def dismiss_habit(habit_key: str) -> bool:
    """Tell the investment service to dismiss a habit. Returns True on success."""
    try:
        r = requests.delete(f"{_BASE}/api/habits/{habit_key}", timeout=_TIMEOUT)
        return r.ok
    except Exception:
        return False
