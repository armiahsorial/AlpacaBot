"""Combine GEX reads with Alpaca option data to rank candidate contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from trading_bot.alpaca_client import AlpacaClient
from trading_bot.analysis import GexAnalysis

OPTIONABLE_GEX_TICKER_OVERRIDES = {
    "SPX": "SPY",
    "NDX": "QQQ",
    "RUT": "IWM",
}


@dataclass(frozen=True)
class OptionCandidate:
    symbol: str
    underlying_symbol: str
    contract_type: str
    expiration_date: str
    strike_price: float
    bid: float | None
    ask: float | None
    mid: float | None
    spread: float | None
    spread_pct: float | None
    open_interest: int | None
    delta: float | None
    gamma: float | None
    implied_volatility: float | None
    score: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "underlying_symbol": self.underlying_symbol,
            "contract_type": self.contract_type,
            "expiration_date": self.expiration_date,
            "strike_price": self.strike_price,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "spread": self.spread,
            "spread_pct": self.spread_pct,
            "open_interest": self.open_interest,
            "delta": self.delta,
            "gamma": self.gamma,
            "implied_volatility": self.implied_volatility,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class OptionRecommendation:
    ticker: str
    underlying_symbol: str
    period: str
    gex_timestamp: int
    gex_spot: float
    bias: str
    contract_type: str | None
    target_level: float | None
    trade_permission: str
    recommendation: str
    candidates: tuple[OptionCandidate, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "underlying_symbol": self.underlying_symbol,
            "period": self.period,
            "gex_timestamp": self.gex_timestamp,
            "gex_spot": self.gex_spot,
            "bias": self.bias,
            "contract_type": self.contract_type,
            "target_level": self.target_level,
            "trade_permission": self.trade_permission,
            "recommendation": self.recommendation,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
        }


def recommend_option_contracts(
    *,
    gex_analysis: GexAnalysis,
    alpaca_client: AlpacaClient,
    max_expiration_days: int = 14,
    max_candidates: int = 5,
) -> OptionRecommendation:
    ticker = gex_analysis.ticker.upper()
    underlying_symbol = OPTIONABLE_GEX_TICKER_OVERRIDES.get(ticker, ticker)
    warnings: list[str] = []

    contract_type = _contract_type_from_bias(gex_analysis.bias)
    if contract_type is None:
        return OptionRecommendation(
            ticker=ticker,
            underlying_symbol=underlying_symbol,
            period=gex_analysis.period,
            gex_timestamp=gex_analysis.timestamp,
            gex_spot=gex_analysis.spot,
            bias=gex_analysis.bias,
            contract_type=None,
            target_level=None,
            trade_permission=gex_analysis.trade_permission,
            recommendation="No option contract selected because the GEX read is neutral.",
            candidates=(),
            warnings=("GEX bias is neutral; wait for directional alignment before selecting calls or puts.",),
        )

    if ticker in OPTIONABLE_GEX_TICKER_OVERRIDES:
        warnings.append(f"{ticker} is not an equity option underlying at Alpaca; using {underlying_symbol} as proxy.")

    if gex_analysis.trade_permission == "no trade":
        warnings.append("GEX trade permission is no trade; candidates are watchlist ideas, not entry instructions.")

    today = date.today()
    contracts = alpaca_client.get_option_contracts(
        underlying_symbol,
        expiration_date_gte=today.isoformat(),
        expiration_date_lte=(today + timedelta(days=max_expiration_days)).isoformat(),
        limit=1000,
    )
    target_level = _target_level(gex_analysis, contract_type)
    side_contracts = _filter_contracts(contracts, contract_type, gex_analysis.spot, target_level)
    snapshots = _load_snapshots(alpaca_client, [contract["symbol"] for contract in side_contracts[:100]])

    candidates = tuple(
        sorted(
            (
                candidate
                for candidate in (
                    _candidate_from_contract(contract, snapshots.get(contract["symbol"], {}), gex_analysis, target_level)
                    for contract in side_contracts
                )
                if candidate is not None
            ),
            key=lambda candidate: candidate.score,
            reverse=True,
        )[:max_candidates]
    )

    if not candidates:
        return OptionRecommendation(
            ticker=ticker,
            underlying_symbol=underlying_symbol,
            period=gex_analysis.period,
            gex_timestamp=gex_analysis.timestamp,
            gex_spot=gex_analysis.spot,
            bias=gex_analysis.bias,
            contract_type=contract_type,
            target_level=target_level,
            trade_permission=gex_analysis.trade_permission,
            recommendation="No liquid option contract candidate was found in the near-dated Alpaca chain.",
            candidates=(),
            warnings=tuple(warnings + ["No candidate had usable bid/ask quote data."]),
        )

    best = candidates[0]
    recommendation = (
        f"Watch {best.symbol}: {best.expiration_date} {best.strike_price:g} "
        f"{best.contract_type} near { _format_mid(best.mid) } mid."
    )

    return OptionRecommendation(
        ticker=ticker,
        underlying_symbol=underlying_symbol,
        period=gex_analysis.period,
        gex_timestamp=gex_analysis.timestamp,
        gex_spot=gex_analysis.spot,
        bias=gex_analysis.bias,
        contract_type=contract_type,
        target_level=target_level,
        trade_permission=gex_analysis.trade_permission,
        recommendation=recommendation,
        candidates=candidates,
        warnings=tuple(warnings),
    )


def _contract_type_from_bias(bias: str) -> str | None:
    if bias in {"bullish", "neutral-bullish"}:
        return "call"
    if bias in {"bearish", "neutral-bearish"}:
        return "put"
    return None


def _target_level(analysis: GexAnalysis, contract_type: str) -> float:
    if contract_type == "call":
        levels = [
            level
            for level in (analysis.classic_major_positive, analysis.state_call_gamma_node)
            if level and level > analysis.spot
        ]
        return min(levels) if levels else analysis.spot

    levels = [
        level
        for level in (analysis.classic_major_negative, analysis.state_put_gamma_node)
        if level and level < analysis.spot
    ]
    return max(levels) if levels else analysis.spot


def _filter_contracts(
    contracts: list[dict[str, Any]],
    contract_type: str,
    spot: float,
    target_level: float,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    min_strike = min(spot, target_level) * 0.96
    max_strike = max(spot, target_level) * 1.04

    for contract in contracts:
        if str(contract.get("type", "")).lower() != contract_type:
            continue
        if str(contract.get("status", "")).lower() != "active":
            continue
        if contract.get("tradable") is False:
            continue
        strike = _to_float(contract.get("strike_price"))
        if strike is None:
            continue
        if min_strike <= strike <= max_strike:
            filtered.append(contract)

    return sorted(filtered, key=lambda contract: abs((_to_float(contract.get("strike_price")) or spot) - target_level))


def _load_snapshots(alpaca_client: AlpacaClient, symbols: list[str]) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for index in range(0, len(symbols), 100):
        snapshots.update(alpaca_client.get_option_snapshots(symbols[index : index + 100]))
    return snapshots


def _candidate_from_contract(
    contract: dict[str, Any],
    snapshot: dict[str, Any],
    analysis: GexAnalysis,
    target_level: float,
) -> OptionCandidate | None:
    quote = snapshot.get("latestQuote") if isinstance(snapshot, dict) else None
    if not isinstance(quote, dict):
        return None

    bid = _to_float(quote.get("bp"))
    ask = _to_float(quote.get("ap"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None

    strike = _to_float(contract.get("strike_price"))
    if strike is None:
        return None

    mid = (bid + ask) / 2
    spread = ask - bid
    spread_pct = spread / mid if mid else None
    greeks = snapshot.get("greeks") if isinstance(snapshot, dict) else None
    greeks = greeks if isinstance(greeks, dict) else {}
    contract_type = str(contract.get("type", "")).lower()
    open_interest = _to_int(contract.get("open_interest"))
    delta = _to_float(greeks.get("delta"))
    gamma = _to_float(greeks.get("gamma"))
    iv = _to_float(snapshot.get("impliedVolatility")) if isinstance(snapshot, dict) else None

    score = 100.0
    reasons: list[str] = []

    target_distance = abs(strike - target_level)
    score -= min(target_distance / max(analysis.spot * 0.01, 1), 20)
    reasons.append(f"Strike is {target_distance:g} from GEX target level {target_level:g}.")

    if spread_pct is not None:
        score -= min(spread_pct * 100, 35)
        reasons.append(f"Spread is {spread_pct:.1%} of mid.")
        if spread_pct <= 0.15:
            score += 8
            reasons.append("Bid/ask spread is acceptable for a watchlist candidate.")

    if open_interest is not None:
        oi_bonus = min(open_interest / 250, 12)
        score += oi_bonus
        reasons.append(f"Open interest is {open_interest}.")

    if delta is not None:
        desired_delta = 0.45 if contract_type == "call" else -0.45
        score -= min(abs(delta - desired_delta) * 25, 15)
        reasons.append(f"Delta is {delta:g}.")

    if analysis.trade_permission == "no trade":
        score -= 20
        reasons.append("GEX says no trade, so this is watchlist-only.")

    return OptionCandidate(
        symbol=str(contract.get("symbol", "")).upper(),
        underlying_symbol=str(contract.get("underlying_symbol", analysis.ticker)).upper(),
        contract_type=contract_type,
        expiration_date=str(contract.get("expiration_date", "")),
        strike_price=strike,
        bid=bid,
        ask=ask,
        mid=mid,
        spread=spread,
        spread_pct=spread_pct,
        open_interest=open_interest,
        delta=delta,
        gamma=gamma,
        implied_volatility=iv,
        score=score,
        reasons=tuple(reasons),
    )


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


def _format_mid(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"${value:.2f}"
