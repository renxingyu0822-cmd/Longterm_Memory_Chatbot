"""Transparent trend probabilities, risk metrics, backtests, and simulations.

The first version intentionally uses an explainable statistical score instead of
letting an LLM invent market probabilities. It is an experimental research
signal and must be evaluated per asset class before being treated as useful.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

import numpy as np


HORIZONS = (1, 3, 5, 20)
MODEL_VERSION = "transparent-momentum-v1"
OTC_FUND_MODEL_VERSION = "otc-nav-direction-v1"


def _clean_prices(values: Iterable[float]) -> list[float]:
    prices = []
    for value in values:
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            prices.append(price)
    return prices


def _softmax(scores: Iterable[float]) -> list[float]:
    array = np.asarray(list(scores), dtype=float)
    array -= np.max(array)
    exponentials = np.exp(array)
    probabilities = exponentials / np.sum(exponentials)
    return [float(item) for item in probabilities]


def _daily_volatility(prices: list[float], window: int = 60) -> float:
    if len(prices) < 3:
        return 0.015
    subset = np.asarray(prices[-(window + 1) :], dtype=float)
    returns = np.diff(np.log(subset))
    volatility = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.015
    return max(volatility, 0.002)


def _return_over(prices: list[float], days: int) -> float:
    if len(prices) <= days:
        return 0.0
    return prices[-1] / prices[-1 - days] - 1


def _one_prediction(prices: list[float], horizon: int) -> dict:
    current = prices[-1]
    volatility = _daily_volatility(prices)
    horizon_volatility = volatility * math.sqrt(horizon)

    short_days = min(max(horizon, 1), len(prices) - 1)
    medium_days = min(max(horizon * 3, 5), 20, len(prices) - 1)
    short_return = _return_over(prices, short_days)
    medium_return = _return_over(prices, medium_days)

    fast_window = min(5, len(prices))
    slow_window = min(20, len(prices))
    fast_mean = float(np.mean(prices[-fast_window:]))
    slow_mean = float(np.mean(prices[-slow_window:]))
    trend_gap = fast_mean / slow_mean - 1 if slow_mean else 0

    normalized = (
        0.52 * short_return
        + 0.30 * medium_return
        + 0.18 * trend_gap
    ) / max(horizon_volatility, 0.006)
    normalized = float(np.clip(normalized, -2.2, 2.2))

    # A modest neutral prior keeps tiny moves from becoming false certainty.
    neutral_score = 0.52 - min(abs(normalized) * 0.10, 0.22)
    probability_up, probability_flat, probability_down = _softmax(
        (normalized * 0.42, neutral_score, -normalized * 0.42)
    )
    maximum = max(probability_up, probability_flat, probability_down)
    confidence = "high" if maximum >= 0.64 else "medium" if maximum >= 0.50 else "low"
    interval = 1.28 * horizon_volatility

    return {
        "horizon_days": horizon,
        "probability_up": probability_up,
        "probability_flat": probability_flat,
        "probability_down": probability_down,
        "expected_low": (math.exp(-interval) - 1) * 100,
        "expected_high": (math.exp(interval) - 1) * 100,
        "confidence": confidence,
        "drivers": {
            "short_momentum": short_return * 100,
            "medium_momentum": medium_return * 100,
            "trend_gap": trend_gap * 100,
            "daily_volatility": volatility * 100,
        },
    }


def predict_trends(prices: Iterable[float], current_price: float | None = None) -> list[dict]:
    cleaned = _clean_prices(prices)
    if current_price is not None and float(current_price) > 0:
        current = float(current_price)
        if not cleaned or not math.isclose(cleaned[-1], current, rel_tol=1e-10):
            cleaned.append(current)
    if len(cleaned) < 25:
        return []
    return [_one_prediction(cleaned, horizon) for horizon in HORIZONS]


def _one_otc_fund_prediction(prices: list[float], horizon: int) -> dict:
    """Predict a future published NAV relative to the current published NAV.

    An OTC fund has one official NAV per trading day rather than a tradable
    intraday open. The current NAV therefore serves as the forecast period's
    start reference, and the NAV published after ``horizon`` trading days is
    its end value.
    """

    prediction = _one_prediction(prices, horizon)
    directional_total = prediction["probability_up"] + prediction["probability_down"]
    if directional_total <= 0:
        probability_up = probability_down = 0.5
    else:
        probability_up = prediction["probability_up"] / directional_total
        probability_down = prediction["probability_down"] / directional_total
    maximum = max(probability_up, probability_down)
    prediction.update(
        {
            "probability_up": probability_up,
            "probability_flat": 0.0,
            "probability_down": probability_down,
            "confidence": "high" if maximum >= 0.68 else "medium" if maximum >= 0.58 else "low",
            "target_definition": "period_end_nav_vs_period_start_nav",
        }
    )
    return prediction


def predict_otc_fund_direction(
    prices: Iterable[float],
    current_price: float | None = None,
) -> list[dict]:
    """Return binary direction forecasts for each OTC-fund horizon."""

    cleaned = _clean_prices(prices)
    if current_price is not None and float(current_price) > 0:
        current = float(current_price)
        if not cleaned or not math.isclose(cleaned[-1], current, rel_tol=1e-10):
            cleaned.append(current)
    if len(cleaned) < 25:
        return []
    return [_one_otc_fund_prediction(cleaned, horizon) for horizon in HORIZONS]


def risk_metrics(prices: Iterable[float]) -> dict:
    cleaned = _clean_prices(prices)
    if len(cleaned) < 3:
        return {
            "annualized_volatility": None,
            "max_drawdown": None,
            "downside_frequency": None,
            "risk_level": "insufficient_data",
        }
    values = np.asarray(cleaned, dtype=float)
    simple_returns = values[1:] / values[:-1] - 1
    annualized_volatility = float(np.std(simple_returns, ddof=1) * math.sqrt(252) * 100)
    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1
    max_drawdown = float(np.min(drawdowns) * 100)
    downside_frequency = float(np.mean(simple_returns < 0) * 100)
    risk_level = "high" if annualized_volatility >= 35 else "medium" if annualized_volatility >= 18 else "low"
    return {
        "annualized_volatility": annualized_volatility,
        "max_drawdown": max_drawdown,
        "downside_frequency": downside_frequency,
        "risk_level": risk_level,
    }


def _actual_class(prices: list[float], index: int, horizon: int) -> str:
    actual_return = prices[index + horizon] / prices[index] - 1
    local = prices[max(0, index - 60) : index + 1]
    neutral_band = _daily_volatility(local) * math.sqrt(horizon) * 0.22
    if actual_return > neutral_band:
        return "up"
    if actual_return < -neutral_band:
        return "down"
    return "flat"


def backtest(prices: Iterable[float], max_samples: int = 260) -> dict[str, dict]:
    cleaned = _clean_prices(prices)
    output: dict[str, dict] = {}
    if len(cleaned) < 90:
        return output

    for horizon in HORIZONS:
        start = max(60, len(cleaned) - max_samples - horizon)
        predicted_labels: list[str] = []
        actual_labels: list[str] = []
        high_confidence_correct = 0
        high_confidence_count = 0
        for index in range(start, len(cleaned) - horizon):
            prediction = _one_prediction(cleaned[: index + 1], horizon)
            probabilities = {
                "up": prediction["probability_up"],
                "flat": prediction["probability_flat"],
                "down": prediction["probability_down"],
            }
            predicted = max(probabilities, key=probabilities.get)
            actual = _actual_class(cleaned, index, horizon)
            predicted_labels.append(predicted)
            actual_labels.append(actual)
            if max(probabilities.values()) >= 0.55:
                high_confidence_count += 1
                high_confidence_correct += int(predicted == actual)

        sample_count = len(actual_labels)
        correct = sum(p == a for p, a in zip(predicted_labels, actual_labels))
        recalls = []
        for label in ("up", "flat", "down"):
            actual_count = sum(value == label for value in actual_labels)
            if actual_count:
                recalls.append(
                    sum(p == label and a == label for p, a in zip(predicted_labels, actual_labels))
                    / actual_count
                )
        output[str(horizon)] = {
            "sample_count": sample_count,
            "accuracy": correct / sample_count * 100 if sample_count else None,
            "balanced_accuracy": float(np.mean(recalls) * 100) if recalls else None,
            "high_confidence_accuracy": (
                high_confidence_correct / high_confidence_count * 100
                if high_confidence_count
                else None
            ),
            "high_confidence_coverage": (
                high_confidence_count / sample_count * 100 if sample_count else None
            ),
            "actual_distribution": dict(Counter(actual_labels)),
        }
    return output


def backtest_otc_fund_direction(
    prices: Iterable[float],
    max_samples: int = 260,
) -> dict[str, dict]:
    """Walk-forward test period-end versus period-start OTC NAV direction."""

    cleaned = _clean_prices(prices)
    if len(cleaned) < 90:
        return {}

    output: dict[str, dict] = {}
    for horizon in HORIZONS:
        start = max(60, len(cleaned) - max_samples - horizon)
        predicted_labels: list[str] = []
        actual_labels: list[str] = []
        high_confidence_correct = 0
        high_confidence_count = 0
        for index in range(start, len(cleaned) - horizon):
            actual_return = cleaned[index + horizon] / cleaned[index] - 1
            # Unchanged NAV observations do not have an up/down ground-truth label.
            if math.isclose(actual_return, 0.0, abs_tol=1e-12):
                continue
            prediction = _one_otc_fund_prediction(cleaned[: index + 1], horizon)
            probabilities = {
                "up": prediction["probability_up"],
                "down": prediction["probability_down"],
            }
            predicted = max(probabilities, key=probabilities.get)
            actual = "up" if actual_return > 0 else "down"
            predicted_labels.append(predicted)
            actual_labels.append(actual)
            if max(probabilities.values()) >= 0.58:
                high_confidence_count += 1
                high_confidence_correct += int(predicted == actual)

        sample_count = len(actual_labels)
        correct = sum(p == a for p, a in zip(predicted_labels, actual_labels))
        recalls = []
        for label in ("up", "down"):
            actual_count = sum(value == label for value in actual_labels)
            if actual_count:
                recalls.append(
                    sum(p == label and a == label for p, a in zip(predicted_labels, actual_labels))
                    / actual_count
                )
        output[str(horizon)] = {
            "sample_count": sample_count,
            "accuracy": correct / sample_count * 100 if sample_count else None,
            "balanced_accuracy": float(np.mean(recalls) * 100) if recalls else None,
            "high_confidence_accuracy": (
                high_confidence_correct / high_confidence_count * 100
                if high_confidence_count
                else None
            ),
            "high_confidence_coverage": (
                high_confidence_count / sample_count * 100 if sample_count else None
            ),
            "actual_distribution": dict(Counter(actual_labels)),
        }
    return output


def _max_drawdown(equity_curve: list[float]) -> float:
    values = np.asarray(equity_curve, dtype=float)
    peaks = np.maximum.accumulate(values)
    return float(np.min(values / peaks - 1) * 100)


def simulate_probability_strategy(
    prices: Iterable[float],
    threshold: float = 0.55,
    transaction_cost: float = 0.001,
) -> dict:
    cleaned = _clean_prices(prices)
    if len(cleaned) < 90:
        return {}
    start = max(60, len(cleaned) - 260)
    equity = 1.0
    buy_hold = 1.0
    position = 0.0
    turnover = 0.0
    equity_curve = [equity]
    for index in range(start, len(cleaned) - 1):
        prediction = _one_prediction(cleaned[: index + 1], 5)
        target_position = 1.0 if prediction["probability_up"] >= threshold else 0.0
        trade = abs(target_position - position)
        if trade:
            equity *= 1 - transaction_cost * trade
            turnover += trade
        next_return = cleaned[index + 1] / cleaned[index] - 1
        equity *= 1 + target_position * next_return
        buy_hold *= 1 + next_return
        position = target_position
        equity_curve.append(equity)
    return {
        "name": "probability_threshold",
        "threshold": threshold,
        "transaction_cost": transaction_cost,
        "sample_days": len(equity_curve) - 1,
        "strategy_return": (equity - 1) * 100,
        "buy_hold_return": (buy_hold - 1) * 100,
        "excess_return": (equity - buy_hold) * 100,
        "max_drawdown": _max_drawdown(equity_curve),
        "turnover": turnover,
        "disclaimer": "历史模拟，不代表未来收益",
    }
