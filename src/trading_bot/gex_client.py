"""Client for the GEX API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from trading_bot.config import Settings

AGGREGATION_PERIODS = ("full", "zero", "one")
STATE_GREEKS = (
    "delta_zero",
    "gamma_zero",
    "delta_one",
    "gamma_one",
    "charm_zero",
    "vanna_zero",
    "charm_one",
    "vanna_one",
)


class GexApiError(RuntimeError):
    """Raised when the GEX API returns an error or invalid response."""


@dataclass(frozen=True)
class Tickers:
    stocks: tuple[str, ...]
    indexes: tuple[str, ...]
    futures: tuple[str, ...]

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Tickers":
        return cls(
            stocks=_read_symbol_list(payload, "stocks"),
            indexes=_read_symbol_list(payload, "indexes"),
            futures=_read_symbol_list(payload, "futures"),
        )

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "stocks": list(self.stocks),
            "indexes": list(self.indexes),
            "futures": list(self.futures),
        }


@dataclass(frozen=True)
class GexStrike:
    strike: float
    gex_by_volume: float
    gex_by_open_interest: float
    priors: tuple[float, ...]

    @classmethod
    def from_json(cls, value: Any) -> "GexStrike":
        if not isinstance(value, list) or len(value) != 4:
            raise GexApiError("Expected each strike row to be [strike, gex volume, gex open interest, priors].")

        priors = value[3]
        if not isinstance(priors, list):
            raise GexApiError("Expected strike priors to be an array.")

        return cls(
            strike=_read_number(value[0], "strike"),
            gex_by_volume=_read_number(value[1], "gex by volume"),
            gex_by_open_interest=_read_number(value[2], "gex by open interest"),
            priors=tuple(_read_number(item, "strike prior") for item in priors),
        )

    def as_list(self) -> list[Any]:
        return [
            self.strike,
            self.gex_by_volume,
            self.gex_by_open_interest,
            list(self.priors),
        ]


@dataclass(frozen=True)
class GexChain:
    timestamp: int
    ticker: str
    min_dte: int
    sec_min_dte: int
    spot: float
    zero_gamma: float
    major_pos_vol: float
    major_pos_oi: float
    major_neg_vol: float
    major_neg_oi: float
    strikes: tuple[GexStrike, ...]
    sum_gex_vol: float
    sum_gex_oi: float
    delta_risk_reversal: float
    max_priors: tuple[tuple[float, float], ...]

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "GexChain":
        strikes = payload.get("strikes")
        if not isinstance(strikes, list):
            raise GexApiError("Expected 'strikes' to be an array.")

        max_priors = payload.get("max_priors")
        if not isinstance(max_priors, list):
            raise GexApiError("Expected 'max_priors' to be an array.")

        return cls(
            timestamp=_read_int(payload, "timestamp"),
            ticker=_read_string(payload, "ticker").upper(),
            min_dte=_read_int(payload, "min_dte"),
            sec_min_dte=_read_int(payload, "sec_min_dte"),
            spot=_read_number(payload.get("spot"), "spot"),
            zero_gamma=_read_number(payload.get("zero_gamma"), "zero_gamma"),
            major_pos_vol=_read_number(payload.get("major_pos_vol"), "major_pos_vol"),
            major_pos_oi=_read_number(payload.get("major_pos_oi"), "major_pos_oi"),
            major_neg_vol=_read_number(payload.get("major_neg_vol"), "major_neg_vol"),
            major_neg_oi=_read_number(payload.get("major_neg_oi"), "major_neg_oi"),
            strikes=tuple(GexStrike.from_json(item) for item in strikes),
            sum_gex_vol=_read_number(payload.get("sum_gex_vol"), "sum_gex_vol"),
            sum_gex_oi=_read_number(payload.get("sum_gex_oi"), "sum_gex_oi"),
            delta_risk_reversal=_read_number(payload.get("delta_risk_reversal"), "delta_risk_reversal"),
            max_priors=tuple(_read_pair(item, "max_priors") for item in max_priors),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "min_dte": self.min_dte,
            "sec_min_dte": self.sec_min_dte,
            "spot": self.spot,
            "zero_gamma": self.zero_gamma,
            "major_pos_vol": self.major_pos_vol,
            "major_pos_oi": self.major_pos_oi,
            "major_neg_vol": self.major_neg_vol,
            "major_neg_oi": self.major_neg_oi,
            "strikes": [strike.as_list() for strike in self.strikes],
            "sum_gex_vol": self.sum_gex_vol,
            "sum_gex_oi": self.sum_gex_oi,
            "delta_risk_reversal": self.delta_risk_reversal,
            "max_priors": [list(pair) for pair in self.max_priors],
        }


@dataclass(frozen=True)
class GexMajorLevels:
    timestamp: int
    ticker: str
    spot: float
    mpos_vol: float
    mpos_oi: float
    mneg_vol: float
    mneg_oi: float
    zero_gamma: float
    net_gex_vol: float
    net_gex_oi: float

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "GexMajorLevels":
        return cls(
            timestamp=_read_int(payload, "timestamp"),
            ticker=_read_string(payload, "ticker").upper(),
            spot=_read_number(payload.get("spot"), "spot"),
            mpos_vol=_read_number(payload.get("mpos_vol"), "mpos_vol"),
            mpos_oi=_read_number(payload.get("mpos_oi"), "mpos_oi"),
            mneg_vol=_read_number(payload.get("mneg_vol"), "mneg_vol"),
            mneg_oi=_read_number(payload.get("mneg_oi"), "mneg_oi"),
            zero_gamma=_read_number(payload.get("zero_gamma"), "zero_gamma"),
            net_gex_vol=_read_number(payload.get("net_gex_vol"), "net_gex_vol"),
            net_gex_oi=_read_number(payload.get("net_gex_oi"), "net_gex_oi"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "spot": self.spot,
            "mpos_vol": self.mpos_vol,
            "mpos_oi": self.mpos_oi,
            "mneg_vol": self.mneg_vol,
            "mneg_oi": self.mneg_oi,
            "zero_gamma": self.zero_gamma,
            "net_gex_vol": self.net_gex_vol,
            "net_gex_oi": self.net_gex_oi,
        }


@dataclass(frozen=True)
class GexChange:
    strike: float
    value: float

    @classmethod
    def from_json(cls, value: Any, field_name: str) -> "GexChange":
        strike, gex_value = _read_pair(value, field_name)
        return cls(strike=strike, value=gex_value)

    def as_list(self) -> list[float]:
        return [self.strike, self.value]


@dataclass(frozen=True)
class GexMaxChange:
    timestamp: int
    ticker: str
    current: GexChange
    one: GexChange
    five: GexChange
    ten: GexChange
    fifteen: GexChange
    thirty: GexChange

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "GexMaxChange":
        return cls(
            timestamp=_read_int(payload, "timestamp"),
            ticker=_read_string(payload, "ticker").upper(),
            current=GexChange.from_json(payload.get("current"), "current"),
            one=GexChange.from_json(payload.get("one"), "one"),
            five=GexChange.from_json(payload.get("five"), "five"),
            ten=GexChange.from_json(payload.get("ten"), "ten"),
            fifteen=GexChange.from_json(payload.get("fifteen"), "fifteen"),
            thirty=GexChange.from_json(payload.get("thirty"), "thirty"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "current": self.current.as_list(),
            "one": self.one.as_list(),
            "five": self.five.as_list(),
            "ten": self.ten.as_list(),
            "fifteen": self.fifteen.as_list(),
            "thirty": self.thirty.as_list(),
        }


@dataclass(frozen=True)
class StateGreekMiniContract:
    strike: float
    call_ivol: float
    put_ivol: float
    greek_value: float
    priors: tuple[float, ...]
    extra: tuple[Any, ...]

    @classmethod
    def from_json(cls, value: Any) -> "StateGreekMiniContract":
        if not isinstance(value, list) or len(value) < 5:
            raise GexApiError(
                "Expected each mini contract row to be [strike, call ivol, put ivol, greek value, priors]."
            )

        priors = value[4]
        if not isinstance(priors, list):
            raise GexApiError("Expected mini contract priors to be an array.")

        return cls(
            strike=_read_number(value[0], "mini contract strike"),
            call_ivol=_read_number(value[1], "mini contract call ivol"),
            put_ivol=_read_number(value[2], "mini contract put ivol"),
            greek_value=_read_number(value[3], "mini contract greek value"),
            priors=tuple(_read_number(item, "mini contract prior") for item in priors),
            extra=tuple(value[5:]),
        )

    def as_list(self) -> list[Any]:
        return [
            self.strike,
            self.call_ivol,
            self.put_ivol,
            self.greek_value,
            list(self.priors),
            *self.extra,
        ]


@dataclass(frozen=True)
class StateGreekProfile:
    timestamp: int
    ticker: str
    spot: float
    min_dte: int
    sec_min_dte: int
    major_positive: float
    major_negative: float
    major_long_gamma: float
    major_short_gamma: float
    mini_contracts: tuple[StateGreekMiniContract, ...]

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "StateGreekProfile":
        mini_contracts = payload.get("mini_contracts")
        if not isinstance(mini_contracts, list):
            raise GexApiError("Expected 'mini_contracts' to be an array.")

        return cls(
            timestamp=_read_int(payload, "timestamp"),
            ticker=_read_string(payload, "ticker").upper(),
            spot=_read_number(payload.get("spot"), "spot"),
            min_dte=_read_int(payload, "min_dte"),
            sec_min_dte=_read_int(payload, "sec_min_dte"),
            major_positive=_read_number(payload.get("major_positive"), "major_positive"),
            major_negative=_read_number(payload.get("major_negative"), "major_negative"),
            major_long_gamma=_read_number(payload.get("major_long_gamma"), "major_long_gamma"),
            major_short_gamma=_read_number(payload.get("major_short_gamma"), "major_short_gamma"),
            mini_contracts=tuple(StateGreekMiniContract.from_json(item) for item in mini_contracts),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "spot": self.spot,
            "min_dte": self.min_dte,
            "sec_min_dte": self.sec_min_dte,
            "major_positive": self.major_positive,
            "major_negative": self.major_negative,
            "major_long_gamma": self.major_long_gamma,
            "major_short_gamma": self.major_short_gamma,
            "mini_contracts": [contract.as_list() for contract in self.mini_contracts],
        }


class GexClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_tickers(self) -> Tickers:
        payload = self._get_json("/tickers")
        if not isinstance(payload, dict):
            raise GexApiError("Expected tickers response to be a JSON object.")

        return Tickers.from_json(payload)

    def get_gex_chain(self, ticker: str, aggregation_period: str) -> GexChain:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        safe_ticker = quote(ticker, safe="")
        payload = self._get_json(f"/{safe_ticker}/classic/{aggregation_period}")
        if not isinstance(payload, dict):
            raise GexApiError("Expected GEX chain response to be a JSON object.")

        return GexChain.from_json(payload)

    def get_state_gex_profile(self, ticker: str, aggregation_period: str) -> GexChain:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        safe_ticker = quote(ticker, safe="")
        payload = self._get_json(f"/{safe_ticker}/state/{aggregation_period}")
        if not isinstance(payload, dict):
            raise GexApiError("Expected state GEX profile response to be a JSON object.")

        return GexChain.from_json(payload)

    def get_gex_major_levels(self, ticker: str, aggregation_period: str) -> GexMajorLevels:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        safe_ticker = quote(ticker, safe="")
        payload = self._get_json(f"/{safe_ticker}/classic/{aggregation_period}/majors")
        if not isinstance(payload, dict):
            raise GexApiError("Expected GEX major levels response to be a JSON object.")

        return GexMajorLevels.from_json(payload)

    def get_state_gex_major_levels(self, ticker: str, aggregation_period: str) -> GexMajorLevels:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        safe_ticker = quote(ticker, safe="")
        payload = self._get_json(f"/{safe_ticker}/state/{aggregation_period}/majors")
        if not isinstance(payload, dict):
            raise GexApiError("Expected state GEX major levels response to be a JSON object.")

        return GexMajorLevels.from_json(payload)

    def get_gex_max_change(self, ticker: str, aggregation_period: str) -> GexMaxChange:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        safe_ticker = quote(ticker, safe="")
        payload = self._get_json(f"/{safe_ticker}/classic/{aggregation_period}/maxchange")
        if not isinstance(payload, dict):
            raise GexApiError("Expected GEX max change response to be a JSON object.")

        return GexMaxChange.from_json(payload)

    def get_state_gex_max_change(self, ticker: str, aggregation_period: str) -> GexMaxChange:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        safe_ticker = quote(ticker, safe="")
        payload = self._get_json(f"/{safe_ticker}/state/{aggregation_period}/maxchange")
        if not isinstance(payload, dict):
            raise GexApiError("Expected state GEX max change response to be a JSON object.")

        return GexMaxChange.from_json(payload)

    def get_state_greek_profile(self, ticker: str, greek: str) -> StateGreekProfile:
        ticker = ticker.strip().upper()
        greek = greek.strip().lower()

        if not ticker:
            raise ValueError("ticker is required.")
        if greek not in STATE_GREEKS:
            allowed = ", ".join(STATE_GREEKS)
            raise ValueError(f"greek must be one of: {allowed}.")

        safe_ticker = quote(ticker, safe="")
        payload = self._get_json(f"/{safe_ticker}/state/{greek}")
        if not isinstance(payload, dict):
            raise GexApiError("Expected state Greek profile response to be a JSON object.")

        return StateGreekProfile.from_json(payload)

    def _get_json(self, path: str) -> Any:
        request = Request(
            url=f"{self._settings.base_url}{path}",
            method="GET",
            headers={
                "Authorization": f"Bearer {self._settings.api_key}",
                "User-Agent": self._settings.user_agent,
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=self._settings.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GexApiError(f"GEX API request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise GexApiError(f"GEX API request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise GexApiError("GEX API request timed out.") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise GexApiError("GEX API returned invalid JSON.") from exc


def _read_symbol_list(payload: dict[str, Any], field_name: str) -> tuple[str, ...]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise GexApiError(f"Expected '{field_name}' to be an array.")

    symbols: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise GexApiError(f"Expected '{field_name}' to contain non-empty strings.")
        symbols.append(item.strip().upper())

    return tuple(symbols)


def _normalize_ticker_and_period(ticker: str, aggregation_period: str) -> tuple[str, str]:
    ticker = ticker.strip().upper()
    aggregation_period = aggregation_period.strip().lower()

    if not ticker:
        raise ValueError("ticker is required.")
    if aggregation_period not in AGGREGATION_PERIODS:
        allowed = ", ".join(AGGREGATION_PERIODS)
        raise ValueError(f"aggregation_period must be one of: {allowed}.")

    return ticker, aggregation_period


def _read_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise GexApiError(f"Expected '{field_name}' to be a non-empty string.")
    return value.strip()


def _read_int(payload: dict[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GexApiError(f"Expected '{field_name}' to be an integer.")
    return value


def _read_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GexApiError(f"Expected '{field_name}' to be a number.")
    return float(value)


def _read_pair(value: Any, field_name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise GexApiError(f"Expected '{field_name}' entries to be [strike, value].")
    return (_read_number(value[0], field_name), _read_number(value[1], field_name))
