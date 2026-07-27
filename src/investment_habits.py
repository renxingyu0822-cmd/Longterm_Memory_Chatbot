"""Derive explainable investment habits from persisted user actions.

The rules in this module deliberately describe observable patterns instead of
guessing the user's risk tolerance, financial situation, or future intent.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


MEMORY_ID_PREFIX = "investment-habit:"

_SUBCLASS_LABELS = {
    "cn": "A股",
    "hk": "港股",
    "us": "美股",
    "exchange_traded": "场内基金",
    "otc": "场外基金",
}

_THEME_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "technology",
        "科技主题",
        ("科技", "人工智能", "AI", "5G", "通信", "半导体", "芯片", "科创", "软件", "计算机"),
    ),
    ("consumer", "消费主题", ("消费", "白酒", "食品", "饮料", "家电")),
    ("agriculture", "农业主题", ("农业", "农牧", "养殖", "粮食")),
    ("precious_metals", "贵金属主题", ("黄金", "白银", "贵金属")),
)


def memory_id(habit_key: str) -> str:
    return f"{MEMORY_ID_PREFIX}{habit_key}"


def habit_key_from_memory_id(value: str) -> str | None:
    if not value.startswith(MEMORY_ID_PREFIX):
        return None
    key = value[len(MEMORY_ID_PREFIX):].strip()
    return key or None


def _tracked_assets(
    watchlist: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assets: dict[int, dict[str, Any]] = {}
    for item in [*watchlist, *positions]:
        try:
            asset_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        assets[asset_id] = item
    return list(assets.values())


def _confidence(base: float, share: float) -> float:
    return round(min(0.95, base + share * 0.35), 2)


def derive_investment_habits(
    watchlist: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    transactions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return stable, evidence-backed habits derived from current activity."""

    del transactions  # Reserved for future rules once sufficient genuine history exists.
    tracked = _tracked_assets(watchlist, positions)
    habits: list[dict[str, Any]] = []

    if len(tracked) >= 3:
        subclass_counts = Counter(str(item.get("subclass") or "") for item in tracked)
        leading_subclass, leading_count = subclass_counts.most_common(1)[0]
        share = leading_count / len(tracked)
        if leading_subclass in _SUBCLASS_LABELS and leading_count >= 3 and share >= 0.60:
            label = _SUBCLASS_LABELS[leading_subclass]
            habits.append(
                {
                    "habit_key": "tracked_subclass",
                    "summary": (
                        f"用户当前关注的投资资产以{label}为主"
                        f"（{leading_count}/{len(tracked)}）。这是基于当前自选与持仓的行为记录。"
                    ),
                    "confidence": _confidence(0.55, share),
                    "evidence": {
                        "subclass": leading_subclass,
                        "matching_count": leading_count,
                        "tracked_count": len(tracked),
                        "asset_ids": sorted(int(item["id"]) for item in tracked),
                    },
                }
            )

    if len(positions) >= 2:
        position_counts = Counter(str(item.get("subclass") or "") for item in positions)
        leading_subclass, leading_count = position_counts.most_common(1)[0]
        share = leading_count / len(positions)
        if leading_subclass in _SUBCLASS_LABELS and leading_count >= 2 and share >= 0.67:
            label = _SUBCLASS_LABELS[leading_subclass]
            habits.append(
                {
                    "habit_key": "held_subclass",
                    "summary": (
                        f"用户当前持仓以{label}为主"
                        f"（{leading_count}/{len(positions)}），仅反映已记录的当前持仓。"
                    ),
                    "confidence": _confidence(0.60, share),
                    "evidence": {
                        "subclass": leading_subclass,
                        "matching_count": leading_count,
                        "position_count": len(positions),
                        "asset_ids": sorted(int(item["id"]) for item in positions),
                    },
                }
            )

    if len(tracked) >= 3:
        theme_matches: list[tuple[int, str, str, list[int]]] = []
        for theme_key, theme_label, keywords in _THEME_RULES:
            matching_ids = []
            for item in tracked:
                name = str(item.get("name") or "")
                folded_name = name.casefold()
                if any(keyword.casefold() in folded_name for keyword in keywords):
                    matching_ids.append(int(item["id"]))
            theme_matches.append((len(matching_ids), theme_key, theme_label, matching_ids))
        match_count, theme_key, theme_label, matching_ids = max(
            theme_matches,
            key=lambda item: item[0],
        )
        share = match_count / len(tracked)
        if match_count >= 3 and share >= 0.20:
            habits.append(
                {
                    "habit_key": f"theme_interest:{theme_key}",
                    "summary": (
                        f"用户当前关注的资产中，{theme_label}较多"
                        f"（{match_count}/{len(tracked)}）。"
                    ),
                    "confidence": _confidence(0.48, share),
                    "evidence": {
                        "theme": theme_key,
                        "matching_count": match_count,
                        "tracked_count": len(tracked),
                        "asset_ids": sorted(matching_ids),
                    },
                }
            )

    held_ids = {int(item["id"]) for item in positions}
    watchlist_only_count = sum(
        1 for item in watchlist if int(item["id"]) not in held_ids
    )
    if watchlist_only_count >= 5 and watchlist_only_count >= max(5, len(positions) * 2):
        habits.append(
            {
                "habit_key": "uses_watchlist_before_holding",
                "summary": (
                    "用户会维护较广的观察列表"
                    f"（当前仅观察 {watchlist_only_count} 项、持仓 {len(positions)} 项），"
                    "表现出先观察再决定是否持有的习惯。"
                ),
                "confidence": 0.78,
                "evidence": {
                    "watchlist_only_count": watchlist_only_count,
                    "position_count": len(positions),
                },
            }
        )

    return habits
