"""First-pass GEX market analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_bot.gex_client import GexMajorLevels, GexMaxChange


@dataclass(frozen=True)
class GexAnalysis:
    ticker: str
    period: str
    timestamp: int
    spot: float
    zero_gamma: float
    score: int
    market_regime: str
    bias: str
    confidence: str
    trade_permission: str
    setup: str
    entry_trigger: str
    invalidation: str
    target_zone: str
    avoid_zone: str
    action: str
    risk_note: str
    classic_major_positive: float
    classic_major_negative: float
    state_call_gamma_node: float
    state_put_gamma_node: float
    classic_net_gex: float
    state_net_imbalance: float
    classic_thirty_min_change: tuple[float, float]
    state_thirty_min_change: tuple[float, float]
    distance_to_zero_gamma: float | None
    upside_room: float | None
    downside_room: float | None
    reasons: tuple[str, ...]
    score_breakdown: tuple[str, ...]
    no_trade_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "period": self.period,
            "timestamp": self.timestamp,
            "spot": self.spot,
            "zero_gamma": self.zero_gamma,
            "score": self.score,
            "market_regime": self.market_regime,
            "bias": self.bias,
            "confidence": self.confidence,
            "trade_permission": self.trade_permission,
            "setup": self.setup,
            "entry_trigger": self.entry_trigger,
            "invalidation": self.invalidation,
            "target_zone": self.target_zone,
            "avoid_zone": self.avoid_zone,
            "action": self.action,
            "risk_note": self.risk_note,
            "classic_major_positive": self.classic_major_positive,
            "classic_major_negative": self.classic_major_negative,
            "state_call_gamma_node": self.state_call_gamma_node,
            "state_put_gamma_node": self.state_put_gamma_node,
            "classic_net_gex": self.classic_net_gex,
            "state_net_imbalance": self.state_net_imbalance,
            "classic_thirty_min_change": list(self.classic_thirty_min_change),
            "state_thirty_min_change": list(self.state_thirty_min_change),
            "distance_to_zero_gamma": self.distance_to_zero_gamma,
            "upside_room": self.upside_room,
            "downside_room": self.downside_room,
            "reasons": list(self.reasons),
            "score_breakdown": list(self.score_breakdown),
            "no_trade_reasons": list(self.no_trade_reasons),
        }


def analyze_gex(
    *,
    period: str,
    classic_major_levels: GexMajorLevels,
    state_major_levels: GexMajorLevels,
    classic_max_change: GexMaxChange,
    state_max_change: GexMaxChange,
) -> GexAnalysis:
    score = 0
    reasons: list[str] = []
    score_breakdown: list[str] = []
    no_trade_reasons: list[str] = []

    spot = classic_major_levels.spot
    zero_gamma = classic_major_levels.zero_gamma
    distance_to_zero_gamma = _distance(spot, zero_gamma)
    upside_room = _positive_distance(spot, classic_major_levels.mpos_vol)
    downside_room = _positive_distance(classic_major_levels.mneg_vol, spot)

    if zero_gamma:
        if spot > zero_gamma:
            score += 1
            reasons.append("Spot is above classic zero gamma, which supports a constructive bias.")
            score_breakdown.append("+1 spot above zero gamma")
        elif spot < zero_gamma:
            score -= 1
            reasons.append("Spot is below classic zero gamma, which supports a defensive bias.")
            score_breakdown.append("-1 spot below zero gamma")
        else:
            reasons.append("Spot is exactly at classic zero gamma, so direction is unresolved.")
            score_breakdown.append("0 spot exactly at zero gamma")
    else:
        reasons.append("Classic zero gamma is unavailable or zero.")
        score_breakdown.append("0 zero gamma unavailable")
        no_trade_reasons.append("Classic zero gamma is unavailable.")

    if classic_major_levels.net_gex_vol > 0:
        score += 1
        reasons.append("Classic net GEX by volume is positive.")
        score_breakdown.append("+1 classic net GEX positive")
    elif classic_major_levels.net_gex_vol < 0:
        score -= 1
        reasons.append("Classic net GEX by volume is negative.")
        score_breakdown.append("-1 classic net GEX negative")
    else:
        score_breakdown.append("0 classic net GEX flat")

    if state_major_levels.net_gex_vol > 0:
        score += 1
        reasons.append("State net GEX imbalance is positive.")
        score_breakdown.append("+1 state imbalance positive")
    elif state_major_levels.net_gex_vol < 0:
        score -= 1
        reasons.append("State net GEX imbalance is negative.")
        score_breakdown.append("-1 state imbalance negative")
    else:
        score_breakdown.append("0 state imbalance flat")

    if classic_max_change.thirty.value > 0:
        score += 1
        reasons.append("Classic 30-minute max change is positive.")
        score_breakdown.append("+1 classic 30m max change positive")
    elif classic_max_change.thirty.value < 0:
        score -= 1
        reasons.append("Classic 30-minute max change is negative.")
        score_breakdown.append("-1 classic 30m max change negative")
    else:
        score_breakdown.append("0 classic 30m max change flat")

    if state_max_change.thirty.value > 0:
        score += 1
        reasons.append("State 30-minute max imbalance change is positive.")
        score_breakdown.append("+1 state 30m max imbalance change positive")
    elif state_max_change.thirty.value < 0:
        score -= 1
        reasons.append("State 30-minute max imbalance change is negative.")
        score_breakdown.append("-1 state 30m max imbalance change negative")
    else:
        score_breakdown.append("0 state 30m max imbalance change flat")

    if _is_too_close(spot, classic_major_levels.mpos_vol):
        no_trade_reasons.append("Spot is close to classic major positive GEX; upside chase risk is elevated.")
    if _is_too_close(spot, classic_major_levels.mneg_vol):
        no_trade_reasons.append("Spot is close to classic major negative GEX; downside reaction risk is elevated.")
    if abs(score) <= 1:
        no_trade_reasons.append("Signal alignment is weak.")

    bias = _bias_from_score(score)
    confidence = _confidence_from_score(score)
    market_regime = _market_regime(classic_major_levels, state_major_levels)
    trade_permission = _trade_permission(score, no_trade_reasons)
    setup = _setup_from_bias(bias)
    entry_trigger = _entry_trigger(bias, zero_gamma, state_major_levels)
    invalidation = _invalidation(bias, classic_major_levels, state_major_levels)
    target_zone = _target_zone(bias, classic_major_levels, state_major_levels)
    avoid_zone = _avoid_zone(bias, classic_major_levels, state_major_levels)
    action = _action_from_bias(bias, trade_permission)
    risk_note = _risk_note(classic_major_levels, state_major_levels)

    return GexAnalysis(
        ticker=classic_major_levels.ticker,
        period=period,
        timestamp=classic_major_levels.timestamp,
        spot=spot,
        zero_gamma=zero_gamma,
        score=score,
        market_regime=market_regime,
        bias=bias,
        confidence=confidence,
        trade_permission=trade_permission,
        setup=setup,
        entry_trigger=entry_trigger,
        invalidation=invalidation,
        target_zone=target_zone,
        avoid_zone=avoid_zone,
        action=action,
        risk_note=risk_note,
        classic_major_positive=classic_major_levels.mpos_vol,
        classic_major_negative=classic_major_levels.mneg_vol,
        state_call_gamma_node=state_major_levels.mpos_vol,
        state_put_gamma_node=state_major_levels.mneg_vol,
        classic_net_gex=classic_major_levels.net_gex_vol,
        state_net_imbalance=state_major_levels.net_gex_vol,
        classic_thirty_min_change=(classic_max_change.thirty.strike, classic_max_change.thirty.value),
        state_thirty_min_change=(state_max_change.thirty.strike, state_max_change.thirty.value),
        distance_to_zero_gamma=distance_to_zero_gamma,
        upside_room=upside_room,
        downside_room=downside_room,
        reasons=tuple(reasons),
        score_breakdown=tuple(score_breakdown),
        no_trade_reasons=tuple(no_trade_reasons),
    )


def _bias_from_score(score: int) -> str:
    if score >= 3:
        return "bullish"
    if score >= 1:
        return "neutral-bullish"
    if score <= -3:
        return "bearish"
    if score <= -1:
        return "neutral-bearish"
    return "neutral"


def _confidence_from_score(score: int) -> str:
    absolute_score = abs(score)
    if absolute_score >= 4:
        return "high"
    if absolute_score >= 2:
        return "medium"
    return "low"


def _action_from_bias(bias: str, trade_permission: str) -> str:
    if trade_permission == "no trade":
        return "No trade. Wait for cleaner alignment or more room away from major GEX levels."
    if trade_permission == "wait":
        return "Wait for confirmation before taking directional exposure."
    if bias == "bullish":
        return "Consider bullish setups only after price holds above zero gamma and avoids chasing major positive GEX."
    if bias == "neutral-bullish":
        return "Watch for a hold above zero gamma before considering bullish exposure."
    if bias == "bearish":
        return "Consider bearish setups only after price fails below zero gamma or loses the put gamma node."
    if bias == "neutral-bearish":
        return "Watch for rejection below zero gamma before considering bearish exposure."
    return "No trade signal. Wait for clearer alignment between classic GEX and state imbalance."


def _market_regime(classic_major_levels: GexMajorLevels, state_major_levels: GexMajorLevels) -> str:
    classic_positive = classic_major_levels.net_gex_vol > 0
    state_positive = state_major_levels.net_gex_vol > 0
    if classic_positive and state_positive:
        return "positive gamma with supportive state flow"
    if not classic_positive and not state_positive:
        return "negative gamma with defensive state flow"
    if classic_positive and not state_positive:
        return "positive gamma structure with negative state imbalance"
    return "negative gamma structure with positive state imbalance"


def _trade_permission(score: int, no_trade_reasons: list[str]) -> str:
    if no_trade_reasons:
        return "no trade"
    if abs(score) >= 4:
        return "possible trade after confirmation"
    if abs(score) >= 2:
        return "wait for confirmation"
    return "no trade"


def _setup_from_bias(bias: str) -> str:
    if bias in {"bullish", "neutral-bullish"}:
        return "bullish hold above zero gamma"
    if bias in {"bearish", "neutral-bearish"}:
        return "bearish rejection below zero gamma"
    return "no directional setup"


def _entry_trigger(bias: str, zero_gamma: float, state_major_levels: GexMajorLevels) -> str:
    if bias in {"bullish", "neutral-bullish"}:
        return f"Price holds above {zero_gamma:g} while state imbalance improves or remains positive."
    if bias in {"bearish", "neutral-bearish"}:
        return f"Price rejects below {zero_gamma:g} or loses the put gamma node near {state_major_levels.mneg_vol:g}."
    return "Wait for price to resolve away from zero gamma with aligned state imbalance."


def _invalidation(bias: str, classic_major_levels: GexMajorLevels, state_major_levels: GexMajorLevels) -> str:
    if bias in {"bullish", "neutral-bullish"}:
        return f"Loss of zero gamma near {classic_major_levels.zero_gamma:g} or classic negative near {classic_major_levels.mneg_vol:g}."
    if bias in {"bearish", "neutral-bearish"}:
        return f"Reclaim of zero gamma near {classic_major_levels.zero_gamma:g} or classic positive near {classic_major_levels.mpos_vol:g}."
    return "No active setup, so no invalidation level."


def _target_zone(bias: str, classic_major_levels: GexMajorLevels, state_major_levels: GexMajorLevels) -> str:
    if bias in {"bullish", "neutral-bullish"}:
        return _format_zone(classic_major_levels.mpos_vol, state_major_levels.mpos_vol)
    if bias in {"bearish", "neutral-bearish"}:
        return _format_zone(classic_major_levels.mneg_vol, state_major_levels.mneg_vol)
    return "No target until a directional setup appears."


def _avoid_zone(bias: str, classic_major_levels: GexMajorLevels, state_major_levels: GexMajorLevels) -> str:
    if bias in {"bullish", "neutral-bullish"}:
        return f"Avoid chasing bullish trades into {_format_zone(classic_major_levels.mpos_vol, state_major_levels.mpos_vol)}"
    if bias in {"bearish", "neutral-bearish"}:
        return f"Avoid chasing bearish trades into {_format_zone(classic_major_levels.mneg_vol, state_major_levels.mneg_vol)}"
    return "Avoid directional trades while signals are mixed."


def _format_zone(first: float, second: float) -> str:
    lower = min(first, second)
    upper = max(first, second)
    if lower == upper:
        return f"{lower:g}."
    return f"{lower:g} to {upper:g}."


def _distance(first: float, second: float) -> float | None:
    if not second:
        return None
    return first - second


def _positive_distance(lower: float, upper: float) -> float | None:
    distance = upper - lower
    if distance < 0:
        return None
    return distance


def _is_too_close(spot: float, level: float) -> bool:
    if not level:
        return False
    return abs(spot - level) <= max(3.0, spot * 0.0005)


def _risk_note(classic_major_levels: GexMajorLevels, state_major_levels: GexMajorLevels) -> str:
    return (
        "Treat major positive GEX and state call gamma nodes as potential upside resistance; "
        "treat major negative GEX and state put gamma nodes as potential downside pressure/support zones. "
        "Use defined risk before entering any trade."
    )
