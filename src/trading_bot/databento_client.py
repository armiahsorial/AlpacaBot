"""Databento-backed options and equities market-data adapter."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from threading import Lock, RLock, Thread
from typing import Any, Iterable

from trading_bot.config import DatabentoSettings
from trading_bot.market_data import MarketDataClient, MarketDataError

# The macOS PyArrow mimalloc backend has produced intermittent native crashes
# during Databento frame conversion. This must be set before PyArrow is imported.
os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")

OCC_SYMBOL = re.compile(r"^([A-Z0-9.]+)(\d{6})([CP])(\d{8})$")
AVAILABLE_END_PATTERN = re.compile(
    r"has data available up to ['\"](?P<available_end>[^'\"]+)['\"]",
    re.IGNORECASE,
)
PRICE_SCALE = 1_000_000_000
TIMEFRAME_SCHEMAS = {
    "1min": "ohlcv-1m",
    "1minute": "ohlcv-1m",
    "1day": "ohlcv-1d",
    "1d": "ohlcv-1d",
}
OPTION_PARENT_ROOTS = {
    "SPX": ("SPX", "SPXW"),
    "NDX": ("NDX", "NDXP"),
    "RUT": ("RUT", "RUTW"),
}
AM_SETTLED_INDEX_ROOTS = {"SPX", "NDX", "RUT"}
WEEKLY_INDEX_ROOTS = {"SPX": "SPXW", "NDX": "NDXP", "RUT": "RUTW"}

# PyArrow's native allocator can crash when multiple threaded HTTP requests
# fetch and materialize Databento frames concurrently. Serialize that historical
# path process-wide; live feeds and non-Arrow requests stay parallel.
_HISTORICAL_CONVERSION_LOCK = Lock()


class DatabentoApiError(MarketDataError):
    """Raised when Databento returns an error or unsupported record shape."""


class DatabentoClient:
    """Normalize Databento records to the shape consumed by the application."""

    provider_name = "databento"

    def __init__(
        self,
        settings: DatabentoSettings,
        *,
        equities_fallback: MarketDataClient | None = None,
    ) -> None:
        self._settings = settings
        self._equities_fallback = equities_fallback
        self._client_lock = Lock()
        self._historical_client: Any | None = None
        self._live_option_setup_lock = Lock()
        self._live_option_network_lock = Lock()
        self._live_option_lock = RLock()
        self._live_option_client: Any | None = None
        self._live_option_started = False
        self._live_option_symbols: set[str] = set()
        self._live_option_mappings: dict[int, str] = {}
        self._live_option_snapshots: dict[str, dict[str, Any]] = {}
        self._live_option_setup_error: str | None = None

    def get_latest_bar(self, symbol: str, *, feed: str | None = None) -> dict[str, Any]:
        del feed
        symbol = _clean_symbol(symbol)
        end = datetime.now(timezone.utc)
        bars = self.get_stock_bars(
            symbol,
            start=(end - timedelta(minutes=5)).isoformat(),
            end=end.isoformat(),
            timeframe="1Min",
        )
        return {"bars": {symbol: bars[-1] if bars else {}}}

    def get_stock_bars(
        self,
        symbol: str,
        *,
        start: str,
        end: str,
        timeframe: str = "1Min",
        feed: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        del feed
        symbol = _clean_symbol(symbol)
        if self._equities_fallback is not None:
            return self._equities_fallback.get_stock_bars(
                symbol,
                start=start,
                end=end,
                timeframe=timeframe,
                feed="iex",
                limit=limit,
            )
        try:
            rows = self._bar_rows(
                dataset=self._settings.equities_dataset,
                symbols=[symbol],
                start=start,
                end=end,
                timeframe=timeframe,
                stype_in="raw_symbol",
            )
        except DatabentoApiError:
            raise
        return [_normalize_bar(row) for row in rows[:limit]]

    def get_option_contracts(
        self,
        underlying_symbol: str,
        *,
        expiration_date_gte: str | None = None,
        expiration_date_lte: str | None = None,
        status: str = "active",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        underlying = _clean_symbol(underlying_symbol)
        query_day = date.today()
        rows: list[dict[str, Any]] = []
        parent_errors: list[DatabentoApiError] = []
        for root in OPTION_PARENT_ROOTS.get(underlying, (underlying,)):
            request = {
                "dataset": self._settings.options_dataset,
                "schema": "definition",
                "symbols": [f"{root}.OPT"],
                "stype_in": "parent",
                "start": query_day.isoformat(),
            }
            try:
                rows.extend(
                    self._historical_rows(
                        **request,
                        end=(query_day + timedelta(days=1)).isoformat(),
                    )
                )
            except DatabentoApiError:
                try:
                    rows.extend(self._live_rows(**request))
                except DatabentoApiError as exc:
                    parent_errors.append(exc)
        if not rows and parent_errors:
            raise parent_errors[-1]
        contracts: list[dict[str, Any]] = []
        for row in rows:
            contract = _normalize_contract(row, underlying)
            if contract is None:
                continue
            expiration = contract["expiration_date"]
            if expiration_date_gte and expiration < expiration_date_gte:
                continue
            if expiration_date_lte and expiration > expiration_date_lte:
                continue
            if status and contract["status"] != status.lower():
                continue
            contracts.append(contract)
        unique_contracts = {contract["symbol"]: contract for contract in contracts}
        ordered = sorted(
            unique_contracts.values(),
            key=lambda item: (item["expiration_date"], float(item["strike_price"])),
        )
        return ordered[:limit]

    def get_option_snapshots(self, symbols: list[str], *, feed: str | None = None) -> dict[str, Any]:
        del feed
        clean_symbols = [_clean_symbol(symbol) for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            raise ValueError("symbols are required.")
        now = datetime.now(timezone.utc)
        rows = self._live_rows(
            dataset=self._settings.options_dataset,
            schema="cbbo-1s",
            symbols=[_to_databento_option_symbol(symbol) for symbol in clean_symbols],
            stype_in="raw_symbol",
            start=(now - timedelta(seconds=self._settings.live_replay_seconds)).isoformat(),
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = _from_databento_option_symbol(str(row.get("symbol", "")))
            if symbol not in clean_symbols:
                continue
            quote = _quote_from_row(row)
            if quote is None:
                continue
            snapshot = latest.setdefault(symbol, {})
            snapshot["latestQuote"] = quote
            last = _price(row.get("price"))
            if last is not None:
                snapshot["latestTrade"] = {"p": last, "t": row.get("t")}
        return latest

    def get_streaming_option_snapshots(self, symbols: list[str]) -> dict[str, Any]:
        """Return in-memory one-second option marks from one persistent live session."""
        clean_symbols = [_clean_symbol(symbol) for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            raise ValueError("symbols are required.")
        # Databento may deliver callbacks while start/subscribe is still running.
        # Do not hold the snapshot lock here or the callback and request can deadlock.
        self._ensure_live_option_stream(clean_symbols)
        with self._live_option_setup_lock:
            setup_error = self._live_option_setup_error
        if setup_error:
            raise DatabentoApiError(f"Databento streaming request failed: {setup_error}")
        with self._live_option_lock:
            return {
                symbol: dict(self._live_option_snapshots.get(symbol, {}))
                for symbol in clean_symbols
            }

    def _ensure_live_option_stream(self, symbols: list[str]) -> None:
        with self._live_option_setup_lock:
            new_symbols = [symbol for symbol in symbols if symbol not in self._live_option_symbols]
            if not new_symbols:
                return
            # Reserve these symbols before starting network work so one-second HTTP
            # polling cannot launch duplicate subscriptions while the gateway connects.
            self._live_option_symbols.update(new_symbols)
        Thread(
            target=self._subscribe_live_option_symbols,
            args=(new_symbols,),
            name="databento-option-stream-setup",
            daemon=True,
        ).start()

    def _subscribe_live_option_symbols(self, symbols: list[str]) -> None:
        try:
            # Databento authentication/subscription can take several seconds. Keep it
            # off the HTTP request thread and serialize additions to the live session.
            with self._live_option_network_lock:
                if self._live_option_client is None:
                    db = _databento_module()
                    self._live_option_client = db.Live(key=self._settings.api_key)
                    self._live_option_client.add_callback(self._receive_live_option_record)
                start = None
                if not self._live_option_started:
                    start = (
                        datetime.now(timezone.utc) - timedelta(seconds=self._settings.live_replay_seconds)
                    ).isoformat()
                self._live_option_client.subscribe(
                    dataset=self._settings.options_dataset,
                    schema="cbbo-1s",
                    symbols=[_to_databento_option_symbol(symbol) for symbol in symbols],
                    stype_in="raw_symbol",
                    start=start,
                )
                if not self._live_option_started:
                    self._live_option_client.start()
                    self._live_option_started = True
            with self._live_option_setup_lock:
                self._live_option_setup_error = None
        except Exception as exc:
            with self._live_option_setup_lock:
                self._live_option_symbols.difference_update(symbols)
                self._live_option_setup_error = str(exc)

    def _receive_live_option_record(self, record: Any) -> None:
        instrument_id = _instrument_id(record)
        mapped_symbol = getattr(record, "stype_out_symbol", None)
        with self._live_option_lock:
            if mapped_symbol is not None and instrument_id is not None:
                self._live_option_mappings[instrument_id] = _from_databento_option_symbol(str(mapped_symbol))
                return
            row = _live_record_row(record)
            raw_symbol = self._live_option_mappings.get(
                instrument_id,
                _from_databento_option_symbol(str(row.get("raw_symbol") or row.get("symbol") or "")),
            )
            if not raw_symbol:
                return
            quote = _quote_from_row(row)
            if quote is None:
                return
            snapshot = self._live_option_snapshots.setdefault(raw_symbol, {})
            snapshot["latestQuote"] = quote
            last = _price(row.get("price"))
            if last is not None:
                snapshot["latestTrade"] = {"p": last, "t": row.get("t")}

    def get_option_bars(
        self,
        symbols: list[str],
        *,
        start: str,
        end: str,
        timeframe: str = "1Min",
        feed: str | None = None,
        limit: int = 10000,
    ) -> dict[str, Any]:
        del feed
        clean_symbols = [_clean_symbol(symbol) for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            raise ValueError("symbols are required.")
        rows = self._bar_rows(
            dataset=self._settings.options_dataset,
            symbols=[_to_databento_option_symbol(symbol) for symbol in clean_symbols],
            start=start,
            end=end,
            timeframe=timeframe,
            stype_in="raw_symbol",
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            symbol = _from_databento_option_symbol(str(row.get("symbol", "")))
            if symbol in clean_symbols and len(grouped[symbol]) < limit:
                grouped[symbol].append(_normalize_bar(row))

        # Older signals may have been recorded with the parent index root even
        # though Databento stores that expiration under its weekly root.
        aliases = {
            alias: symbol
            for symbol in clean_symbols
            for alias in [_weekly_option_alias(symbol)]
            if alias is not None
        }
        if aliases:
            alias_rows = self._bar_rows(
                dataset=self._settings.options_dataset,
                symbols=[_to_databento_option_symbol(symbol) for symbol in aliases],
                start=start,
                end=end,
                timeframe=timeframe,
                stype_in="raw_symbol",
            )
            alias_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in alias_rows:
                alias = _from_databento_option_symbol(str(row.get("symbol", "")))
                requested_symbol = aliases.get(alias)
                if requested_symbol and len(alias_grouped[requested_symbol]) < limit:
                    alias_grouped[requested_symbol].append(_normalize_bar(row))
            for requested_symbol, candidate_bars in alias_grouped.items():
                exact_bars = grouped.get(requested_symbol, [])
                exact_latest = max((_row_time(bar) for bar in exact_bars), default=None)
                alias_latest = max((_row_time(bar) for bar in candidate_bars), default=None)
                if candidate_bars and (
                    not exact_bars or
                    (alias_latest is not None and (exact_latest is None or alias_latest > exact_latest))
                ):
                    grouped[requested_symbol] = candidate_bars
        return {symbol: grouped.get(symbol, []) for symbol in clean_symbols}

    def _bar_rows(
        self,
        *,
        dataset: str,
        symbols: list[str],
        start: str,
        end: str,
        timeframe: str,
        stype_in: str,
    ) -> list[dict[str, Any]]:
        schema = TIMEFRAME_SCHEMAS.get(timeframe.strip().lower())
        if schema is None:
            raise ValueError("Databento supports 1Min and 1Day bars in this application.")
        end_dt = _parse_datetime(end)
        if schema == "ohlcv-1m" and end_dt.date() >= datetime.now(timezone.utc).date():
            rows = self._live_rows(
                dataset=dataset,
                schema=schema,
                symbols=symbols,
                stype_in=stype_in,
                start=start,
            )
            return [row for row in rows if _row_time(row) is None or _row_time(row) <= end_dt]
        return self._historical_rows(
            dataset=dataset,
            schema=schema,
            symbols=symbols,
            stype_in=stype_in,
            start=start,
            end=end,
        )

    def _historical_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            # Databento does not support raw_symbol -> raw_symbol resolution.
            # Its DBN metadata maps the default instrument_id output back to the
            # requested OCC symbol when the frame is materialized.
            with _HISTORICAL_CONVERSION_LOCK:
                data = self._historical().timeseries.get_range(**kwargs)
                frame = data.to_df().reset_index()
                records = frame.to_dict(orient="records")
            return [_clean_row(row) for row in records]
        except Exception as exc:
            available_end = _available_end_from_error(exc)
            requested_end = _optional_datetime(kwargs.get("end"))
            requested_start = _optional_datetime(kwargs.get("start"))
            if available_end is not None and requested_end is not None and requested_end > available_end:
                if requested_start is not None and requested_start >= available_end:
                    return []
                retry_kwargs = dict(kwargs)
                retry_kwargs["end"] = available_end.isoformat()
                try:
                    with _HISTORICAL_CONVERSION_LOCK:
                        data = self._historical().timeseries.get_range(**retry_kwargs)
                        frame = data.to_df().reset_index()
                        records = frame.to_dict(orient="records")
                    return [_clean_row(row) for row in records]
                except Exception as retry_exc:
                    raise DatabentoApiError(
                        f"Databento historical request failed after retrying through "
                        f"{available_end.isoformat()}: {retry_exc}"
                    ) from retry_exc
            raise DatabentoApiError(f"Databento historical request failed: {exc}") from exc

    def _live_rows(
        self,
        *,
        dataset: str,
        schema: str,
        symbols: list[str],
        stype_in: str,
        start: str,
    ) -> list[dict[str, Any]]:
        db = _databento_module()
        mappings: dict[int, str] = {}
        rows: list[dict[str, Any]] = []

        def receive(record: Any) -> None:
            instrument_id = _instrument_id(record)
            mapped_symbol = getattr(record, "stype_out_symbol", None)
            if mapped_symbol is not None and instrument_id is not None:
                mappings[instrument_id] = str(mapped_symbol)
                return
            row = _live_record_row(record)
            if instrument_id is not None:
                row["symbol"] = mappings.get(instrument_id, row.get("symbol", ""))
            if row:
                rows.append(row)

        try:
            client = db.Live(key=self._settings.api_key)
            client.subscribe(
                dataset=dataset,
                schema=schema,
                symbols=symbols,
                stype_in=stype_in,
                start=start,
            )
            client.add_callback(receive)
            client.start()
            client.block_for_close(timeout=self._settings.live_timeout_seconds)
            client.stop()
        except Exception as exc:
            raise DatabentoApiError(f"Databento live request failed: {exc}") from exc
        return rows

    def _historical(self) -> Any:
        with self._client_lock:
            if self._historical_client is None:
                self._historical_client = _databento_module().Historical(key=self._settings.api_key)
            return self._historical_client


def _databento_module() -> Any:
    try:
        import databento as db
    except ImportError as exc:
        raise DatabentoApiError(
            "The databento package is not installed. Run: python -m pip install -e ."
        ) from exc
    return db


def _clean_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if not value:
        raise ValueError("symbol is required.")
    return value


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _available_end_from_error(exc: Exception) -> datetime | None:
    match = AVAILABLE_END_PATTERN.search(str(exc))
    if match is None:
        return None
    return _optional_datetime(match.group("available_end"))


def _to_databento_option_symbol(symbol: str) -> str:
    match = OCC_SYMBOL.fullmatch(_clean_symbol(symbol))
    if not match:
        return symbol
    root, expiration, side, strike = match.groups()
    return f"{root:<6}{expiration}{side}{strike}"


def _from_databento_option_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if len(symbol) >= 15 and " " in symbol[:6]:
        value = f"{symbol[:6].strip()}{symbol[6:]}".upper()
    return value.replace(" ", "")


def _weekly_option_alias(symbol: str) -> str | None:
    match = OCC_SYMBOL.fullmatch(_clean_symbol(symbol))
    if not match:
        return None
    root, expiration, side, strike = match.groups()
    weekly_root = WEEKLY_INDEX_ROOTS.get(root)
    if weekly_root is None:
        return None
    return f"{weekly_root}{expiration}{side}{strike}"


def _normalize_contract(row: dict[str, Any], underlying: str) -> dict[str, Any] | None:
    raw_symbol = str(row.get("raw_symbol") or row.get("symbol") or "")
    symbol = _from_databento_option_symbol(raw_symbol)
    match = OCC_SYMBOL.fullmatch(symbol)
    if not match:
        return None
    root, expiration_code, side, strike_code = match.groups()
    expiration_value = row.get("expiration")
    expiration = _date_string(expiration_value) or datetime.strptime(expiration_code, "%y%m%d").date().isoformat()
    expiration_dt = _datetime_value(expiration_value)
    strike = _price(row.get("strike_price"))
    if strike is None:
        strike = int(strike_code) / 1000
    return {
        "symbol": symbol,
        "underlying_symbol": underlying or root,
        "type": "call" if side == "C" else "put",
        "expiration_date": expiration,
        "strike_price": strike,
        "status": "active" if _contract_is_active(expiration, expiration_dt, root) else "inactive",
        "tradable": True,
        "open_interest": _integer(row.get("open_interest")),
    }


def _normalize_bar(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "t": row.get("t") or row.get("ts_event") or row.get("ts_recv"),
        "o": _price(row.get("open") if "open" in row else row.get("o")),
        "h": _price(row.get("high") if "high" in row else row.get("h")),
        "l": _price(row.get("low") if "low" in row else row.get("l")),
        "c": _price(row.get("close") if "close" in row else row.get("c")),
        "v": _integer(row.get("volume") if "volume" in row else row.get("v")),
    }


def _quote_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    bid = _price(row.get("bid_px_00") or row.get("bid_px"))
    ask = _price(row.get("ask_px_00") or row.get("ask_px"))
    if bid is None or ask is None:
        return None
    return {
        "bp": bid,
        "ap": ask,
        "bs": _integer(row.get("bid_sz_00") or row.get("bid_sz")),
        "as": _integer(row.get("ask_sz_00") or row.get("ask_sz")),
        "t": row.get("t") or row.get("ts_event") or row.get("ts_recv"),
    }


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = {str(key): _plain_value(value) for key, value in row.items()}
    symbol = cleaned.get("symbol") or cleaned.get("raw_symbol")
    if symbol is not None:
        cleaned["symbol"] = str(symbol)
    timestamp = cleaned.get("ts_event") or cleaned.get("ts_recv") or cleaned.get("index")
    if timestamp is not None:
        cleaned["t"] = _iso_value(timestamp)
    return cleaned


def _live_record_row(record: Any) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in (
        "open", "high", "low", "close", "volume", "price", "size",
        "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00",
        "raw_symbol", "strike_price", "expiration", "instrument_class", "asset",
    ):
        if hasattr(record, field):
            row[field] = getattr(record, field)
    levels = getattr(record, "levels", None)
    if levels:
        level = levels[0]
        for field in ("bid_px", "ask_px", "bid_sz", "ask_sz"):
            if hasattr(level, field):
                row[f"{field}_00"] = getattr(level, field)
    header = getattr(record, "hd", None)
    if header is not None and hasattr(header, "ts_event"):
        row["ts_event"] = _nanoseconds_iso(getattr(header, "ts_event"))
        row["t"] = row["ts_event"]
    elif hasattr(record, "ts_event"):
        row["ts_event"] = _nanoseconds_iso(getattr(record, "ts_event"))
        row["t"] = row["ts_event"]
    return row


def _instrument_id(record: Any) -> int | None:
    header = getattr(record, "hd", None)
    if header is not None:
        return _integer(getattr(header, "instrument_id", None))
    return _integer(getattr(record, "instrument_id", None))


def _price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if abs(number) >= 10_000_000:
        number /= PRICE_SCALE
    return number


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _plain_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _iso_value(value: Any) -> str:
    plain = _plain_value(value)
    return str(plain).replace("+00:00", "Z")


def _nanoseconds_iso(value: Any) -> str | None:
    nanoseconds = _integer(value)
    if nanoseconds is None:
        return None
    return datetime.fromtimestamp(nanoseconds / PRICE_SCALE, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _date_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, int) and value > 10_000_000_000:
        return datetime.fromtimestamp(value / PRICE_SCALE, tz=timezone.utc).date().isoformat()
    text = _iso_value(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if len(text) >= 10 else None


def _datetime_value(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, int) and value > 10_000_000_000:
        return datetime.fromtimestamp(value / PRICE_SCALE, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(_iso_value(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _contract_is_active(expiration: str, expiration_dt: datetime | None, root: str) -> bool:
    if root in AM_SETTLED_INDEX_ROOTS and expiration_dt is not None:
        return expiration_dt > datetime.now(timezone.utc)
    return expiration >= date.today().isoformat()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _row_time(row: dict[str, Any]) -> datetime | None:
    value = row.get("t") or row.get("ts_event") or row.get("ts_recv")
    if not value:
        return None
    try:
        return _parse_datetime(str(value))
    except ValueError:
        return None
