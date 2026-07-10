"""Replay option candidates through an intraday historical bar stream."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from trading_bot.alpaca_client import AlpacaClient
from trading_bot.options_analysis import OptionRecommendation

MARKET_TZ = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class ReplayCandidate:
    symbol: str
    expiration_date: str
    strike_price: float
    contract_type: str
    last_time: str | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    day_change_pct: float | None
    delta: float | None
    gamma: float | None
    implied_volatility: float | None
    replay_score: float
    price_path: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expiration_date": self.expiration_date,
            "strike_price": self.strike_price,
            "contract_type": self.contract_type,
            "last_time": self.last_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "day_change_pct": self.day_change_pct,
            "delta": self.delta,
            "gamma": self.gamma,
            "implied_volatility": self.implied_volatility,
            "replay_score": round(self.replay_score, 4),
            "price_path": list(self.price_path),
        }


@dataclass(frozen=True)
class OptionReplay:
    date: str
    selected_time: str
    recommendation: dict[str, Any]
    candidates: tuple[ReplayCandidate, ...]
    warning: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "selected_time": self.selected_time,
            "recommendation": self.recommendation,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "warning": self.warning,
        }


def replay_option_recommendation(
    *,
    recommendation: OptionRecommendation,
    alpaca_client: AlpacaClient,
    replay_date: str,
    replay_time: str,
) -> OptionReplay:
    symbols = [candidate.symbol for candidate in recommendation.candidates]
    if not symbols:
        return OptionReplay(
            date=replay_date,
            selected_time=replay_time,
            recommendation=recommendation.as_dict(),
            candidates=(),
            warning="No option candidates are available to replay.",
        )

    start_dt = _market_datetime(replay_date, "09:30")
    selected_dt = _market_datetime(replay_date, replay_time)
    if selected_dt < start_dt:
        selected_dt = start_dt

    bars_by_symbol = alpaca_client.get_option_bars(
        symbols,
        start=start_dt.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        end=selected_dt.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        timeframe="1Min",
    )

    base_by_symbol = {candidate.symbol: candidate for candidate in recommendation.candidates}
    replay_candidates: list[ReplayCandidate] = []
    for symbol, bars in bars_by_symbol.items():
        if not isinstance(bars, list) or not bars:
            continue
        base = base_by_symbol.get(symbol)
        if base is None:
            continue
        first_bar = bars[0]
        last_bar = bars[-1]
        first_open = _to_float(first_bar.get("o"))
        close = _to_float(last_bar.get("c"))
        change_pct = None
        if first_open and close:
            change_pct = (close - first_open) / first_open
        volume = _to_float(last_bar.get("v"))
        replay_score = base.score + ((change_pct or 0) * 100) + min((volume or 0) / 1000, 10)
        price_path = tuple(
            close
            for close in (_to_float(bar.get("c")) for bar in bars if isinstance(bar, dict))
            if close is not None
        )

        replay_candidates.append(
            ReplayCandidate(
                symbol=symbol,
                expiration_date=base.expiration_date,
                strike_price=base.strike_price,
                contract_type=base.contract_type,
                last_time=str(last_bar.get("t")) if last_bar.get("t") else None,
                open=_to_float(last_bar.get("o")),
                high=_to_float(last_bar.get("h")),
                low=_to_float(last_bar.get("l")),
                close=close,
                volume=volume,
                day_change_pct=change_pct,
                delta=base.delta,
                gamma=base.gamma,
                implied_volatility=base.implied_volatility,
                replay_score=replay_score,
                price_path=price_path,
            )
        )

    replay_candidates.sort(key=lambda candidate: candidate.replay_score, reverse=True)
    warning = None
    if not replay_candidates:
        warning = "No historical option bars were found for the selected date and time."

    return OptionReplay(
        date=replay_date,
        selected_time=replay_time,
        recommendation=recommendation.as_dict(),
        candidates=tuple(replay_candidates),
        warning=warning,
    )


def _market_datetime(day: str, clock: str) -> datetime:
    parts = [int(part) for part in clock.split(":")]
    if len(parts) == 2:
        hour, minute = parts
    elif len(parts) == 3:
        hour, minute, _second = parts
    else:
        raise ValueError("clock must use HH:MM or HH:MM:SS.")
    return datetime.combine(datetime.fromisoformat(day).date(), time(hour, minute), tzinfo=MARKET_TZ)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
