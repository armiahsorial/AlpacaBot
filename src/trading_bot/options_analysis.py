"""Combine GEX reads with provider-neutral option data to rank contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from math import erf, exp, log, pi, sqrt
from typing import Any
from zoneinfo import ZoneInfo

from trading_bot.analysis import GexAnalysis
from trading_bot.market_data import MarketDataClient

OPTIONABLE_GEX_TICKER_OVERRIDES = {
    "NDX": "QQQ",
    "RUT": "IWM",
}
MARKET_TZ = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


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
    greeks_estimated: bool
    score: float
    reasons: tuple[str, ...]
    price_path: tuple[float, ...] = ()

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
            "greeks_estimated": self.greeks_estimated,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "price_path": list(self.price_path),
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
    alpaca_client: MarketDataClient,
    max_expiration_days: int = 14,
    max_candidates: int = 5,
    max_contract_cost: float | None = None,
) -> OptionRecommendation:
    ticker = gex_analysis.ticker.upper()
    provider_name = getattr(alpaca_client, "provider_name", "alpaca")
    underlying_symbol = (
        ticker
        if provider_name == "databento"
        else OPTIONABLE_GEX_TICKER_OVERRIDES.get(ticker, ticker)
    )
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

    if underlying_symbol != ticker:
        warnings.append(f"{ticker} uses {underlying_symbol} as its option-data proxy.")

    if gex_analysis.trade_permission == "no trade":
        warnings.append("GEX trade permission is no trade; candidates are watchlist ideas, not entry instructions.")

    today = date.today()
    contracts = alpaca_client.get_option_contracts(
        underlying_symbol,
        expiration_date_gte=today.isoformat(),
        expiration_date_lte=(today + timedelta(days=max_expiration_days)).isoformat(),
        limit=10000,
    )
    target_level = _target_level(gex_analysis, contract_type)
    side_contracts = _filter_contracts(contracts, contract_type, gex_analysis.spot, target_level)
    snapshot_limit = 20 if provider_name == "databento" else 100
    priced_contracts = side_contracts[:snapshot_limit]
    snapshots = _load_snapshots(alpaca_client, [contract["symbol"] for contract in priced_contracts])

    candidates = tuple(
        sorted(
            (
                candidate
                for candidate in (
                    _candidate_from_contract(contract, snapshots.get(contract["symbol"], {}), gex_analysis, target_level)
                    for contract in priced_contracts
                )
                if candidate is not None
                and (
                    max_contract_cost is None
                    or (candidate.mid is not None and candidate.mid * 100 <= max_contract_cost)
                )
            ),
            key=lambda candidate: candidate.score,
            reverse=True,
        )[:max_candidates]
    )
    candidates = _attach_intraday_price_paths(alpaca_client, candidates)

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
            recommendation="No liquid option contract candidate was found in the near-dated option chain.",
            candidates=(),
            warnings=tuple(warnings + [
                "No candidate had usable bid/ask quote data within the selected contract-price limit."
                if max_contract_cost is not None
                else "No candidate had usable bid/ask quote data."
            ]),
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

    return sorted(
        filtered,
        key=lambda contract: (
            str(contract.get("expiration_date", "")),
            abs((_to_float(contract.get("strike_price")) or spot) - target_level),
        ),
    )


def _load_snapshots(alpaca_client: MarketDataClient, symbols: list[str]) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for index in range(0, len(symbols), 100):
        snapshots.update(alpaca_client.get_option_snapshots(symbols[index : index + 100]))
    return snapshots


def _attach_intraday_price_paths(
    alpaca_client: MarketDataClient,
    candidates: tuple[OptionCandidate, ...],
) -> tuple[OptionCandidate, ...]:
    if not candidates:
        return candidates

    today = date.today()
    start_dt = datetime.combine(today, time(9, 30), tzinfo=MARKET_TZ)
    end_dt = datetime.now(MARKET_TZ)
    if end_dt < start_dt:
        return candidates

    try:
        bars_by_symbol = alpaca_client.get_option_bars(
            [candidate.symbol for candidate in candidates],
            start=start_dt.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            end=end_dt.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            timeframe="1Min",
        )
    except Exception:
        return candidates

    hydrated: list[OptionCandidate] = []
    for candidate in candidates:
        bars = bars_by_symbol.get(candidate.symbol, [])
        price_path = tuple(
            close
            for close in (_to_float(bar.get("c")) for bar in bars if isinstance(bar, dict))
            if close is not None
        )
        hydrated.append(replace(candidate, price_path=price_path))
    return tuple(hydrated)


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
    greeks_estimated = False
    if delta is None or gamma is None or iv is None:
        estimate = _estimate_greeks(
            contract_type=contract_type,
            spot=analysis.spot,
            strike=strike,
            expiration_date=str(contract.get("expiration_date", "")),
            option_mid=mid,
            implied_volatility=iv,
        )
        if estimate:
            delta = delta if delta is not None else estimate["delta"]
            gamma = gamma if gamma is not None else estimate["gamma"]
            iv = iv if iv is not None else estimate["implied_volatility"]
            greeks_estimated = True

    score = 100.0
    reasons: list[str] = [f"Underlying spot {analysis.spot:g} is sourced from GEX."]

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
        if greeks_estimated:
            reasons.append("Greeks were estimated from the option mid because the data feed did not supply them.")

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
        greeks_estimated=greeks_estimated,
        score=score,
        reasons=tuple(reasons),
    )


def _estimate_greeks(
    *,
    contract_type: str,
    spot: float,
    strike: float,
    expiration_date: str,
    option_mid: float,
    implied_volatility: float | None,
) -> dict[str, float] | None:
    years = _years_to_expiration(expiration_date)
    if spot <= 0 or strike <= 0 or option_mid <= 0 or years is None or years <= 0:
        return None

    volatility = implied_volatility
    if volatility is None or volatility <= 0:
        volatility = _solve_implied_volatility(
            contract_type=contract_type,
            spot=spot,
            strike=strike,
            years=years,
            option_mid=option_mid,
        )
    if volatility is None or volatility <= 0:
        return None

    delta = _black_scholes_delta(contract_type, spot, strike, years, volatility)
    gamma = _black_scholes_gamma(spot, strike, years, volatility)
    if delta is None or gamma is None:
        return None
    return {
        "delta": delta,
        "gamma": gamma,
        "implied_volatility": volatility,
    }


def _years_to_expiration(expiration_date: str) -> float | None:
    try:
        expiration_day = date.fromisoformat(expiration_date)
    except ValueError:
        return None
    expiration_dt = datetime.combine(expiration_day, time(16, 0), tzinfo=MARKET_TZ)
    seconds = (expiration_dt - datetime.now(MARKET_TZ)).total_seconds()
    return max(seconds, 60) / (365 * 24 * 60 * 60)


def _solve_implied_volatility(
    *,
    contract_type: str,
    spot: float,
    strike: float,
    years: float,
    option_mid: float,
) -> float | None:
    low = 0.01
    high = 5.0
    low_price = _black_scholes_price(contract_type, spot, strike, years, low)
    high_price = _black_scholes_price(contract_type, spot, strike, years, high)
    if low_price is None or high_price is None:
        return None
    if option_mid < low_price or option_mid > high_price:
        return None

    for _ in range(60):
        mid = (low + high) / 2
        price = _black_scholes_price(contract_type, spot, strike, years, mid)
        if price is None:
            return None
        if price < option_mid:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _black_scholes_price(
    contract_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.045,
) -> float | None:
    d1, d2 = _black_scholes_d1_d2(spot, strike, years, volatility, risk_free_rate)
    if d1 is None or d2 is None:
        return None
    discounted_strike = strike * exp(-risk_free_rate * years)
    if contract_type == "call":
        return spot * _normal_cdf(d1) - discounted_strike * _normal_cdf(d2)
    if contract_type == "put":
        return discounted_strike * _normal_cdf(-d2) - spot * _normal_cdf(-d1)
    return None


def _black_scholes_delta(
    contract_type: str,
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.045,
) -> float | None:
    d1, _d2 = _black_scholes_d1_d2(spot, strike, years, volatility, risk_free_rate)
    if d1 is None:
        return None
    if contract_type == "call":
        return _normal_cdf(d1)
    if contract_type == "put":
        return _normal_cdf(d1) - 1
    return None


def _black_scholes_gamma(
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float = 0.045,
) -> float | None:
    d1, _d2 = _black_scholes_d1_d2(spot, strike, years, volatility, risk_free_rate)
    if d1 is None or spot <= 0 or volatility <= 0 or years <= 0:
        return None
    return _normal_pdf(d1) / (spot * volatility * sqrt(years))


def _black_scholes_d1_d2(
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float,
) -> tuple[float | None, float | None]:
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        return None, None
    denominator = volatility * sqrt(years)
    d1 = (log(spot / strike) + (risk_free_rate + (volatility**2 / 2)) * years) / denominator
    d2 = d1 - denominator
    return d1, d2


def _normal_cdf(value: float) -> float:
    return (1 + erf(value / sqrt(2))) / 2


def _normal_pdf(value: float) -> float:
    return exp(-(value**2) / 2) / sqrt(2 * pi)


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
