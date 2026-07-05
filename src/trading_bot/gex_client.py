"""Client for the GEX API."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
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
MARKET_TZ = ZoneInfo("America/New_York")
HISTORY_CACHE_DIR = Path.cwd() / ".cache" / "gexbot_history"
_HISTORICAL_ROWS_CACHE: dict[str, list[dict[str, Any]]] = {}
_HISTORICAL_ROW_CACHE: dict[str, dict[str, Any]] = {}
_HISTORICAL_URL_CACHE: dict[str, str] = {}
_GEX_HISTORY_RATE_LIMITED_UNTIL = 0.0
GEX_HISTORY_RATE_LIMIT_COOLDOWN_SECONDS = 60 * 60


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

    def get_historical_gex_inputs(
        self,
        ticker: str,
        aggregation_period: str,
        replay_date: str,
        replay_time: str,
    ) -> tuple[GexMajorLevels, GexMajorLevels, GexMaxChange, GexMaxChange]:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        target_timestamp = _market_timestamp(replay_date, replay_time)
        classic_chain = self._get_historical_chain(ticker, "classic", aggregation_period, replay_date, target_timestamp)
        state_chain = self._get_historical_chain(ticker, "state", aggregation_period, replay_date, target_timestamp)
        return (
            _major_levels_from_chain(classic_chain),
            _major_levels_from_chain(state_chain),
            _max_change_from_chain(classic_chain),
            _max_change_from_chain(state_chain),
        )

    def validate_historical_gex_date(self, ticker: str, aggregation_period: str, replay_date: str) -> dict[str, Any]:
        ticker, aggregation_period = _normalize_ticker_and_period(ticker, aggregation_period)
        safe_ticker = quote(ticker, safe="")
        safe_period = quote(aggregation_period, safe="")

        classic_payload = self._get_json(f"/hist/{safe_ticker}/classic/{safe_period}/{quote(replay_date, safe='')}?noredirect")
        state_payload = self._get_json(f"/hist/{safe_ticker}/state/{safe_period}/{quote(replay_date, safe='')}?noredirect")
        return {
            "ticker": ticker,
            "period": aggregation_period,
            "date": replay_date,
            "classic_available": isinstance(classic_payload, dict) and isinstance(classic_payload.get("url"), str),
            "state_available": isinstance(state_payload, dict) and isinstance(state_payload.get("url"), str),
        }

    def _get_json(self, path: str) -> Any:
        global _GEX_HISTORY_RATE_LIMITED_UNTIL
        if path.startswith("/hist/") and time.time() < _GEX_HISTORY_RATE_LIMITED_UNTIL:
            remaining = int(_GEX_HISTORY_RATE_LIMITED_UNTIL - time.time())
            raise GexApiError(
                "GEX historical replay is cooling down after a rate-limit response. "
                f"Try again in about {max(1, remaining // 60)} minutes."
            )

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
            if exc.code == 429 and path.startswith("/hist/"):
                _GEX_HISTORY_RATE_LIMITED_UNTIL = time.time() + GEX_HISTORY_RATE_LIMIT_COOLDOWN_SECONDS
            raise GexApiError(f"GEX API request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise GexApiError(f"GEX API request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise GexApiError("GEX API request timed out.") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise GexApiError("GEX API returned invalid JSON.") from exc

    def _get_historical_chain(
        self,
        ticker: str,
        mode: str,
        aggregation_period: str,
        replay_date: str,
        target_timestamp: int,
    ) -> GexChain:
        safe_ticker = quote(ticker, safe="")
        safe_mode = quote(mode, safe="")
        safe_period = quote(aggregation_period, safe="")
        safe_date = quote(replay_date, safe="")
        history_key = f"{ticker}:{mode}:{aggregation_period}:{replay_date}"
        row_key = f"{history_key}:{target_timestamp}"
        rows = _HISTORICAL_ROWS_CACHE.get(history_key)
        if rows is None:
            rows = _read_disk_history_cache(history_key)
        if rows is not None:
            selected = _select_historical_row(rows, target_timestamp)
            return GexChain.from_json(selected)

        selected = _HISTORICAL_ROW_CACHE.get(row_key) or _read_disk_history_row(row_key)
        if selected is None:
            url = self._get_historical_signed_url(
                history_key=history_key,
                safe_ticker=safe_ticker,
                safe_mode=safe_mode,
                safe_period=safe_period,
                safe_date=safe_date,
            )

            try:
                selected = self._get_signed_history_row(url, target_timestamp)
            except GexApiError as exc:
                if not _is_expired_signed_url_error(exc):
                    raise
                _HISTORICAL_URL_CACHE.pop(history_key, None)
                url = self._get_historical_signed_url(
                    history_key=history_key,
                    safe_ticker=safe_ticker,
                    safe_mode=safe_mode,
                    safe_period=safe_period,
                    safe_date=safe_date,
                )
                selected = self._get_signed_history_row(url, target_timestamp)
            _HISTORICAL_ROW_CACHE[row_key] = selected
            _write_disk_history_row(row_key, selected)
        return GexChain.from_json(selected)

    def _get_historical_signed_url(
        self,
        *,
        history_key: str,
        safe_ticker: str,
        safe_mode: str,
        safe_period: str,
        safe_date: str,
    ) -> str:
        url = _HISTORICAL_URL_CACHE.get(history_key)
        if url is not None:
            return url

        payload = self._get_json(f"/hist/{safe_ticker}/{safe_mode}/{safe_period}/{safe_date}?noredirect")
        if not isinstance(payload, dict) or not isinstance(payload.get("url"), str):
            raise GexApiError("Expected GEX historical endpoint to return a signed URL.")
        url = payload["url"]
        _HISTORICAL_URL_CACHE[history_key] = url
        return url

    def _get_signed_history_rows(self, url: str) -> list[dict[str, Any]]:
        try:
            with urlopen(url, timeout=max(self._settings.timeout_seconds, 120.0)) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GexApiError(f"GEX historical file request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise GexApiError(f"GEX historical file request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise GexApiError("GEX historical file request timed out.") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GexApiError("GEX historical file returned invalid JSON.") from exc

        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise GexApiError("Expected GEX historical file to contain an array of rows.")
        return payload

    def _get_signed_history_row(self, url: str, target_timestamp: int) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        buffer = ""
        selected: dict[str, Any] | None = None
        first_row: dict[str, Any] | None = None
        array_started = False

        try:
            with urlopen(url, timeout=max(self._settings.timeout_seconds, 120.0)) as response:
                while True:
                    chunk = response.read(65536).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buffer += chunk

                    while True:
                        buffer = buffer.lstrip()
                        if not array_started:
                            if not buffer:
                                break
                            if buffer[0] != "[":
                                raise GexApiError("Expected GEX historical file to contain a JSON array.")
                            buffer = buffer[1:]
                            array_started = True
                            continue

                        buffer = buffer.lstrip()
                        if buffer.startswith(","):
                            buffer = buffer[1:]
                            continue
                        if buffer.startswith("]"):
                            return selected or first_row or _raise_no_historical_rows()
                        if not buffer:
                            break

                        try:
                            row, end_index = decoder.raw_decode(buffer)
                        except json.JSONDecodeError:
                            break

                        if not isinstance(row, dict):
                            raise GexApiError("Expected GEX historical rows to be JSON objects.")
                        first_row = first_row or row

                        timestamp = row.get("timestamp")
                        if isinstance(timestamp, int) and timestamp <= target_timestamp:
                            selected = row
                        elif selected is not None:
                            return selected

                        buffer = buffer[end_index:]
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GexApiError(f"GEX historical file request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise GexApiError(f"GEX historical file request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise GexApiError("GEX historical file request timed out.") from exc

        return selected or first_row or _raise_no_historical_rows()


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


def _major_levels_from_chain(chain: GexChain) -> GexMajorLevels:
    return GexMajorLevels(
        timestamp=chain.timestamp,
        ticker=chain.ticker,
        spot=chain.spot,
        mpos_vol=chain.major_pos_vol,
        mpos_oi=chain.major_pos_oi,
        mneg_vol=chain.major_neg_vol,
        mneg_oi=chain.major_neg_oi,
        zero_gamma=chain.zero_gamma,
        net_gex_vol=chain.sum_gex_vol,
        net_gex_oi=chain.sum_gex_oi,
    )


def _max_change_from_chain(chain: GexChain) -> GexMaxChange:
    priors = list(chain.max_priors)
    while len(priors) < 6:
        priors.append((0.0, 0.0))

    return GexMaxChange(
        timestamp=chain.timestamp,
        ticker=chain.ticker,
        current=GexChange(strike=priors[0][0], value=priors[0][1]),
        one=GexChange(strike=priors[1][0], value=priors[1][1]),
        five=GexChange(strike=priors[2][0], value=priors[2][1]),
        ten=GexChange(strike=priors[3][0], value=priors[3][1]),
        fifteen=GexChange(strike=priors[4][0], value=priors[4][1]),
        thirty=GexChange(strike=priors[5][0], value=priors[5][1]),
    )


def _select_historical_row(rows: list[dict[str, Any]], target_timestamp: int) -> dict[str, Any]:
    selected: dict[str, Any] | None = None
    for row in rows:
        timestamp = row.get("timestamp")
        if not isinstance(timestamp, int):
            continue
        if timestamp <= target_timestamp:
            selected = row
        elif selected is not None:
            break

    if selected is not None:
        return selected

    for row in rows:
        if isinstance(row.get("timestamp"), int):
            return row

    raise GexApiError("GEX historical rows did not include timestamps.")


def _is_expired_signed_url_error(error: GexApiError) -> bool:
    message = str(error).lower()
    return (
        "http 403" in message
        and (
            "authenticationfailed" in message
            or "signed expiry time" in message
            or "server failed to authenticate the request" in message
        )
    )


def _market_timestamp(day: str, clock: str) -> int:
    parts = [int(part) for part in clock.split(":")]
    if len(parts) == 2:
        hour, minute = parts
        second = 0
    elif len(parts) == 3:
        hour, minute, second = parts
    else:
        raise ValueError("time must use HH:MM or HH:MM:SS.")
    value = datetime.fromisoformat(day).replace(hour=hour, minute=minute, second=second, microsecond=0, tzinfo=MARKET_TZ)
    return int(value.timestamp())


def _read_disk_history_cache(history_key: str) -> list[dict[str, Any]] | None:
    path = _history_cache_path(history_key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        return None
    _HISTORICAL_ROWS_CACHE[history_key] = payload
    return payload


def _read_disk_history_row(row_key: str) -> dict[str, Any] | None:
    path = _history_row_cache_path(row_key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    _HISTORICAL_ROW_CACHE[row_key] = payload
    return payload


def _write_disk_history_cache(history_key: str, rows: list[dict[str, Any]]) -> None:
    try:
        HISTORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _history_cache_path(history_key).write_text(json.dumps(rows), encoding="utf-8")
    except OSError:
        return


def _write_disk_history_row(row_key: str, row: dict[str, Any]) -> None:
    try:
        path = _history_row_cache_path(row_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row), encoding="utf-8")
    except OSError:
        return


def _history_cache_path(history_key: str) -> Path:
    safe_name = history_key.replace(":", "_").replace("/", "_")
    return HISTORY_CACHE_DIR / f"{safe_name}.json"


def _history_row_cache_path(row_key: str) -> Path:
    safe_name = row_key.replace(":", "_").replace("/", "_")
    return HISTORY_CACHE_DIR / "rows" / f"{safe_name}.json"


def _raise_no_historical_rows() -> dict[str, Any]:
    raise GexApiError("No GEX historical rows found in historical file.")
