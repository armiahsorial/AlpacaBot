"""Stock technical indicators used as context for trade selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StockTechnicals:
    symbol: str
    as_of: str
    last_price: float | None
    vwap: float | None
    sma_50: float | None
    sma_200: float | None
    fibonacci_levels: dict[str, float]
    fibonacci_near_sma_200: dict[str, float | str] | None
    intraday_volume: int
    score_adjustment: int
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "last_price": self.last_price,
            "vwap": self.vwap,
            "sma_50": self.sma_50,
            "sma_200": self.sma_200,
            "fibonacci_levels": self.fibonacci_levels,
            "fibonacci_near_sma_200": self.fibonacci_near_sma_200,
            "intraday_volume": self.intraday_volume,
            "score_adjustment": self.score_adjustment,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


def calculate_stock_technicals(
    *,
    symbol: str,
    as_of: str,
    minute_bars: list[dict[str, Any]],
    daily_bars: list[dict[str, Any]],
) -> StockTechnicals:
    warnings: list[str] = []
    reasons: list[str] = []

    last_price = _last_close(minute_bars) or _last_close(daily_bars)
    vwap = _intraday_vwap(minute_bars)
    sma_50 = _sma(daily_bars, 50)
    sma_200 = _sma(daily_bars, 200)
    fibonacci_levels = _fibonacci_levels(daily_bars, 200)
    fibonacci_near_sma_200 = _nearest_fibonacci_level(fibonacci_levels, sma_200)
    intraday_volume = sum(_to_int(bar.get("v")) or 0 for bar in minute_bars)

    score_adjustment = 0
    if last_price is None:
        warnings.append("No stock price bars were available for technical context.")
    if vwap is None:
        warnings.append("VWAP is unavailable because no intraday volume bars were available.")
    elif last_price is not None:
        if last_price > vwap:
            score_adjustment += 1
            reasons.append("Price is above VWAP, so buyers have intraday control.")
        elif last_price < vwap:
            score_adjustment -= 1
            reasons.append("Price is below VWAP, so sellers have intraday control.")
        else:
            reasons.append("Price is sitting exactly at VWAP, so intraday control is unresolved.")

    if sma_50 is None:
        warnings.append("50-day moving average is unavailable because fewer than 50 daily bars were returned.")
    elif last_price is not None:
        if last_price > sma_50:
            score_adjustment += 1
            reasons.append("Price is above the 50-day moving average.")
        elif last_price < sma_50:
            score_adjustment -= 1
            reasons.append("Price is below the 50-day moving average.")

    if sma_200 is None:
        warnings.append("200-day moving average is unavailable because fewer than 200 daily bars were returned.")
    elif sma_50 is not None:
        if sma_50 > sma_200:
            score_adjustment += 1
            reasons.append("The 50-day moving average is above the 200-day moving average.")
        elif sma_50 < sma_200:
            score_adjustment -= 1
            reasons.append("The 50-day moving average is below the 200-day moving average.")

    if not fibonacci_levels:
        warnings.append("Fibonacci levels are unavailable because the 200-day daily range could not be calculated.")
    elif fibonacci_near_sma_200 is not None:
        distance_pct = _to_float(fibonacci_near_sma_200.get("distance_pct"))
        label = str(fibonacci_near_sma_200.get("label"))
        level = _to_float(fibonacci_near_sma_200.get("level"))
        if distance_pct is not None and level is not None and distance_pct <= 0.01:
            reasons.append(f"The 200-day moving average is lining up near the {label} Fibonacci level at {level:.2f}.")

    return StockTechnicals(
        symbol=symbol.strip().upper(),
        as_of=as_of,
        last_price=last_price,
        vwap=vwap,
        sma_50=sma_50,
        sma_200=sma_200,
        fibonacci_levels=fibonacci_levels,
        fibonacci_near_sma_200=fibonacci_near_sma_200,
        intraday_volume=intraday_volume,
        score_adjustment=score_adjustment,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _intraday_vwap(bars: list[dict[str, Any]]) -> float | None:
    total_price_volume = 0.0
    total_volume = 0

    for bar in bars:
        volume = _to_int(bar.get("v")) or 0
        if volume <= 0:
            continue
        bar_vwap = _to_float(bar.get("vw"))
        price = bar_vwap if bar_vwap is not None else _typical_price(bar)
        if price is None:
            continue
        total_price_volume += price * volume
        total_volume += volume

    if total_volume <= 0:
        return None
    return total_price_volume / total_volume


def _sma(bars: list[dict[str, Any]], length: int) -> float | None:
    closes = [_to_float(bar.get("c")) for bar in bars]
    closes = [close for close in closes if close is not None]
    if len(closes) < length:
        return None
    window = closes[-length:]
    return sum(window) / length


def _fibonacci_levels(bars: list[dict[str, Any]], length: int) -> dict[str, float]:
    window = bars[-length:] if len(bars) >= length else bars
    highs = [_to_float(bar.get("h")) for bar in window]
    lows = [_to_float(bar.get("l")) for bar in window]
    highs = [high for high in highs if high is not None]
    lows = [low for low in lows if low is not None]
    if not highs or not lows:
        return {}

    high = max(highs)
    low = min(lows)
    price_range = high - low
    if price_range <= 0:
        return {}

    ratios = {
        "0%": 0.0,
        "23.6%": 0.236,
        "38.2%": 0.382,
        "50%": 0.5,
        "61.8%": 0.618,
        "78.6%": 0.786,
        "100%": 1.0,
    }
    return {label: high - (price_range * ratio) for label, ratio in ratios.items()}


def _nearest_fibonacci_level(
    fibonacci_levels: dict[str, float],
    reference: float | None,
) -> dict[str, float | str] | None:
    if not fibonacci_levels or reference is None:
        return None

    label, level = min(fibonacci_levels.items(), key=lambda item: abs(item[1] - reference))
    distance = abs(level - reference)
    distance_pct = distance / reference if reference else 0.0
    return {
        "label": label,
        "level": level,
        "reference": reference,
        "distance": distance,
        "distance_pct": distance_pct,
    }


def _last_close(bars: list[dict[str, Any]]) -> float | None:
    for bar in reversed(bars):
        close = _to_float(bar.get("c"))
        if close is not None:
            return close
    return None


def _typical_price(bar: dict[str, Any]) -> float | None:
    high = _to_float(bar.get("h"))
    low = _to_float(bar.get("l"))
    close = _to_float(bar.get("c"))
    if high is None or low is None or close is None:
        return close
    return (high + low + close) / 3


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)
