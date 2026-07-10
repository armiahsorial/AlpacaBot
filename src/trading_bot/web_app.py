"""Local web UI for trading_bot."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlparse

from trading_bot.alpaca_client import AlpacaApiError, AlpacaClient, PaperOrderRequest
from trading_bot.analysis import analyze_gex
from trading_bot.config import AlpacaSettings, Settings
from trading_bot.gex_client import AGGREGATION_PERIODS, GexApiError, GexClient
from trading_bot.options_analysis import _black_scholes_delta, _black_scholes_gamma, _solve_implied_volatility, recommend_option_contracts
from trading_bot.options_replay import replay_option_recommendation
from trading_bot.technicals import StockTechnicals, calculate_stock_technicals


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_DIR = Path(__file__).parent / "static"
EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
DEFAULT_STOCK_DATA_FEED = "iex"
TECHNICAL_UNDERLYING_OVERRIDES = {
    "SPX": "SPY",
    "NDX": "QQQ",
    "RUT": "IWM",
}


class TradingBotWebHandler(BaseHTTPRequestHandler):
    server_version = "trading_bot/0.1.0"

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/":
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return

        if parsed_url.path == "/styles.css":
            self._send_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return

        if parsed_url.path == "/app.js":
            self._send_file(STATIC_DIR / "app.js", "text/javascript; charset=utf-8")
            return

        if parsed_url.path == "/api/analyze":
            self._handle_analyze(parsed_url.query)
            return

        if parsed_url.path == "/api/alpaca/account":
            self._handle_alpaca_account()
            return

        if parsed_url.path == "/api/alpaca/positions":
            self._handle_alpaca_positions()
            return

        if parsed_url.path == "/api/alpaca/orders":
            self._handle_alpaca_orders(parsed_url.query)
            return

        if parsed_url.path == "/api/alpaca/latest-bar":
            self._handle_alpaca_latest_bar(parsed_url.query)
            return

        if parsed_url.path == "/api/options/recommend":
            self._handle_option_recommendation(parsed_url.query)
            return

        if parsed_url.path == "/api/options/prices":
            self._handle_option_prices(parsed_url.query)
            return

        if parsed_url.path == "/api/options/replay":
            self._handle_option_replay(parsed_url.query)
            return

        if parsed_url.path == "/api/options/replay/validate":
            self._handle_option_replay_validate(parsed_url.query)
            return

        self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/api/alpaca/orders":
            self._handle_submit_alpaca_order()
            return

        if parsed_url.path == "/api/options/outcomes":
            self._handle_option_outcomes()
            return

        self._send_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_analyze(self, query: str) -> None:
        params = parse_qs(query)
        ticker = params.get("ticker", ["SPX"])[0].strip().upper()
        period = params.get("period", ["zero"])[0].strip().lower()

        try:
            if period not in AGGREGATION_PERIODS:
                allowed = ", ".join(AGGREGATION_PERIODS)
                raise ValueError(f"period must be one of: {allowed}.")

            settings = Settings.from_env()
            client = GexClient(settings)
            analysis = analyze_gex(
                period=period,
                classic_major_levels=client.get_gex_major_levels(ticker, period),
                state_major_levels=client.get_state_gex_major_levels(ticker, period),
                classic_max_change=client.get_gex_max_change(ticker, period),
                state_max_change=client.get_state_gex_max_change(ticker, period),
            )
        except (GexApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        payload = analysis.as_dict()
        self._send_json(payload)

    def _handle_alpaca_account(self) -> None:
        try:
            self._send_json(_alpaca_client().get_account())
        except (AlpacaApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_alpaca_positions(self) -> None:
        try:
            self._send_json({"positions": _alpaca_client().get_positions()})
        except (AlpacaApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_alpaca_orders(self, query: str) -> None:
        params = parse_qs(query)
        status = params.get("status", ["open"])[0].strip().lower() or "open"
        limit_raw = params.get("limit", ["50"])[0]

        try:
            limit = int(limit_raw)
            self._send_json({"orders": _alpaca_client().get_orders(status=status, limit=limit)})
        except (AlpacaApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_alpaca_latest_bar(self, query: str) -> None:
        params = parse_qs(query)
        symbol = params.get("symbol", ["SPY"])[0].strip().upper()
        feed = params.get("feed", [""])[0].strip().lower() or None

        try:
            self._send_json(_alpaca_client().get_latest_bar(symbol, feed=feed))
        except (AlpacaApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_option_recommendation(self, query: str) -> None:
        params = parse_qs(query)
        ticker = params.get("ticker", ["AAPL"])[0].strip().upper()
        period = params.get("period", ["zero"])[0].strip().lower()
        max_expiration_days_raw = params.get("max_expiration_days", ["14"])[0]
        limit_raw = params.get("limit", ["5"])[0]

        try:
            if period not in AGGREGATION_PERIODS:
                allowed = ", ".join(AGGREGATION_PERIODS)
                raise ValueError(f"period must be one of: {allowed}.")

            analysis = _analyze_ticker(ticker, period)
            recommendation = recommend_option_contracts(
                gex_analysis=analysis,
                alpaca_client=_alpaca_client(),
                max_expiration_days=int(max_expiration_days_raw),
                max_candidates=int(limit_raw),
            )
        except (AlpacaApiError, GexApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        payload = recommendation.as_dict()
        payload["analysis"] = analysis.as_dict()
        self._send_json(payload)

    def _handle_option_prices(self, query: str) -> None:
        params = parse_qs(query)
        symbols_raw = params.get("symbols", [""])[0]
        symbols = [symbol.strip().upper() for symbol in symbols_raw.split(",") if symbol.strip()]

        try:
            if not symbols:
                raise ValueError("symbols are required.")
            if len(symbols) > 100:
                raise ValueError("At most 100 option symbols can be priced at once.")
            snapshots = _alpaca_client().get_option_snapshots(symbols)
        except (AlpacaApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        prices = {
            symbol: _option_price_from_snapshot(snapshots.get(symbol, {}))
            for symbol in symbols
        }
        self._send_json({"prices": prices})

    def _handle_option_replay(self, query: str) -> None:
        params = parse_qs(query)
        ticker = params.get("ticker", ["AAPL"])[0].strip().upper()
        period = params.get("period", ["zero"])[0].strip().lower()
        replay_date = params.get("date", [""])[0].strip()
        replay_time = params.get("time", ["15:59"])[0].strip()
        max_expiration_days_raw = params.get("max_expiration_days", ["14"])[0]
        limit_raw = params.get("limit", ["5"])[0]

        try:
            if not replay_date:
                raise ValueError("date is required.")
            if period not in AGGREGATION_PERIODS:
                allowed = ", ".join(AGGREGATION_PERIODS)
                raise ValueError(f"period must be one of: {allowed}.")
            alpaca_client = _alpaca_client()
            analysis = _analyze_ticker(ticker, period, replay_date=replay_date, replay_time=replay_time)
            recommendation = recommend_option_contracts(
                gex_analysis=analysis,
                alpaca_client=alpaca_client,
                max_expiration_days=int(max_expiration_days_raw),
                max_candidates=int(limit_raw),
            )
            replay = replay_option_recommendation(
                recommendation=recommendation,
                alpaca_client=alpaca_client,
                replay_date=replay_date,
                replay_time=replay_time,
            )
        except (AlpacaApiError, GexApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        payload = replay.as_dict()
        payload["analysis"] = analysis.as_dict()
        self._send_json(payload)

    def _handle_option_replay_validate(self, query: str) -> None:
        params = parse_qs(query)
        ticker = params.get("ticker", ["AAPL"])[0].strip().upper()
        period = params.get("period", ["zero"])[0].strip().lower()
        replay_date = params.get("date", [""])[0].strip()

        try:
            if not replay_date:
                raise ValueError("date is required.")
            if period not in AGGREGATION_PERIODS:
                allowed = ", ".join(AGGREGATION_PERIODS)
                raise ValueError(f"period must be one of: {allowed}.")
            payload = GexClient(Settings.from_env()).validate_historical_gex_date(ticker, period, replay_date)
        except (GexApiError, ValueError) as exc:
            self._send_json(
                {
                    "valid": False,
                    "ticker": ticker,
                    "period": period,
                    "date": replay_date,
                    "error": str(exc),
                }
            )
            return

        valid = bool(payload["classic_available"] and payload["state_available"])
        self._send_json({"valid": valid, **payload})

    def _handle_submit_alpaca_order(self) -> None:
        try:
            payload = self._read_json_body()
            order = PaperOrderRequest(
                symbol=str(payload.get("symbol", "")),
                side=str(payload.get("side", "")),
                qty=_optional_float(payload.get("qty")),
                notional=_optional_float(payload.get("notional")),
                type=str(payload.get("type", "market")),
                time_in_force=str(payload.get("time_in_force", "day")),
                limit_price=_optional_float(payload.get("limit_price")),
                stop_price=_optional_float(payload.get("stop_price")),
            )
            self._send_json(_alpaca_client().submit_order(order), status=HTTPStatus.CREATED)
        except (AlpacaApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_option_outcomes(self) -> None:
        try:
            payload = self._read_json_body()
            entries = payload.get("entries")
            if not isinstance(entries, list) or not entries:
                raise ValueError("entries are required.")
            if len(entries) > 100:
                raise ValueError("At most 100 option entries can be evaluated at once.")
            outcomes = _option_outcomes(_alpaca_client(), entries)
            self._send_json({"outcomes": outcomes})
        except (AlpacaApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self._send_json({"error": "File not found."}, status=HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("JSON request body is required.")

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), TradingBotWebHandler)
    print(f"trading_bot web UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


def _alpaca_client() -> AlpacaClient:
    return AlpacaClient(AlpacaSettings.from_env())


def _analyze_ticker(ticker: str, period: str, replay_date: str | None = None, replay_time: str | None = None):
    settings = Settings.from_env()
    client = GexClient(settings)
    technicals = _stock_technicals(ticker, replay_date=replay_date, replay_time=replay_time)
    if replay_date and replay_time:
        (
            classic_major_levels,
            state_major_levels,
            classic_max_change,
            state_max_change,
        ) = client.get_historical_gex_inputs(ticker, period, replay_date, replay_time)
        return analyze_gex(
            period=period,
            classic_major_levels=classic_major_levels,
            state_major_levels=state_major_levels,
            classic_max_change=classic_max_change,
            state_max_change=state_max_change,
            technicals=technicals,
        )

    return analyze_gex(
        period=period,
        classic_major_levels=client.get_gex_major_levels(ticker, period),
        state_major_levels=client.get_state_gex_major_levels(ticker, period),
        classic_max_change=client.get_gex_max_change(ticker, period),
        state_max_change=client.get_state_gex_max_change(ticker, period),
        technicals=technicals,
    )


def _stock_technicals(ticker: str, replay_date: str | None = None, replay_time: str | None = None) -> StockTechnicals:
    alpaca_client = _alpaca_client()
    ticker = ticker.strip().upper()
    symbol = TECHNICAL_UNDERLYING_OVERRIDES.get(ticker, ticker)
    as_of = _technical_as_of(replay_date, replay_time)
    market_open = datetime.combine(as_of.date(), time(9, 30), tzinfo=EASTERN)
    daily_start = as_of.date() - timedelta(days=360)
    daily_end = as_of.date()

    minute_bars = alpaca_client.get_stock_bars(
        symbol,
        start=_to_utc_iso(market_open),
        end=_to_utc_iso(as_of),
        timeframe="1Min",
        feed=DEFAULT_STOCK_DATA_FEED,
        limit=10000,
    )
    daily_bars = alpaca_client.get_stock_bars(
        symbol,
        start=daily_start.isoformat(),
        end=daily_end.isoformat(),
        timeframe="1Day",
        feed=DEFAULT_STOCK_DATA_FEED,
        limit=300,
    )
    return calculate_stock_technicals(
        symbol=symbol,
        as_of=as_of.isoformat(),
        minute_bars=minute_bars,
        daily_bars=daily_bars,
    )


def _option_outcomes(alpaca_client: AlpacaClient, raw_entries: list[object]) -> dict[str, dict[str, object]]:
    entries = [_normalize_option_outcome_entry(entry) for entry in raw_entries]
    entries = [entry for entry in entries if entry is not None]
    if not entries:
        raise ValueError("entries did not include any usable option symbols.")

    outcomes: dict[str, dict[str, object]] = {}
    for outcome_date in sorted({entry["date"] for entry in entries}):
        date_entries = [entry for entry in entries if entry["date"] == outcome_date]
        symbols = sorted({entry["symbol"] for entry in date_entries})
        start_dt = min(entry["start_dt"] for entry in date_entries)
        end_dt = _option_outcome_end_dt(outcome_date)
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(minutes=1)

        try:
            option_bars = alpaca_client.get_option_bars(
                symbols,
                start=_to_utc_iso(start_dt),
                end=_to_utc_iso(end_dt),
                timeframe="1Min",
            )
            option_bars_error = None
        except AlpacaApiError as exc:
            option_bars = {}
            option_bars_error = str(exc)
        stock_bars_by_underlying = _load_outcome_stock_bars(alpaca_client, date_entries, start_dt, end_dt)

        for entry in date_entries:
            bars = [
                bar
                for bar in option_bars.get(entry["symbol"], [])
                if isinstance(bar, dict) and (_bar_datetime(bar) is None or _bar_datetime(bar) >= entry["start_dt"])
            ]
            if bars:
                outcomes[entry["id"]] = _outcome_for_entry(entry, bars, stock_bars_by_underlying.get(entry["underlying"], []))
            else:
                outcomes[entry["id"]] = _fallback_outcome_for_entry(entry, option_bars_error)

    return outcomes


def _normalize_option_outcome_entry(entry: object) -> dict[str, object] | None:
    if not isinstance(entry, dict):
        return None
    symbol = str(entry.get("symbol", "")).strip().upper()
    if not symbol:
        return None
    outcome_date = str(entry.get("date", "")).strip()
    timestamp_iso = str(entry.get("timestamp_iso", "")).strip()
    start_dt = _entry_start_datetime(outcome_date, timestamp_iso)
    underlying = str(entry.get("underlying", "")).strip().upper() or _underlying_from_option_symbol(symbol)
    return {
        "id": str(entry.get("id") or symbol),
        "symbol": symbol,
        "date": outcome_date or start_dt.date().isoformat(),
        "start_dt": start_dt,
        "underlying": underlying,
        "expiration_date": str(entry.get("expiration_date", "")).strip(),
        "strike_price": _optional_snapshot_float(entry.get("strike_price")),
        "contract_type": str(entry.get("contract_type", "")).strip().lower(),
        "entry_price": _optional_snapshot_float(entry.get("entry_price")),
        "entry_iv": _optional_snapshot_float(entry.get("entry_iv")),
        "entry_spot": _optional_snapshot_float(entry.get("entry_spot")),
        "fallback_path": [
            value
            for value in (_optional_snapshot_float(value) for value in _as_list(entry.get("fallback_path")))
            if value is not None
        ],
        "fallback_delta": _optional_snapshot_float(entry.get("fallback_delta")),
        "fallback_gamma": _optional_snapshot_float(entry.get("fallback_gamma")),
    }


def _entry_start_datetime(outcome_date: str, timestamp_iso: str) -> datetime:
    if timestamp_iso:
        value = timestamp_iso.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=EASTERN)
            return parsed.astimezone(EASTERN)
        except ValueError:
            pass
    if not outcome_date:
        raise ValueError("entry date or timestamp is required.")
    return datetime.combine(date.fromisoformat(outcome_date), time(9, 30), tzinfo=EASTERN)


def _option_outcome_end_dt(outcome_date: str) -> datetime:
    day = date.fromisoformat(outcome_date)
    session_close = datetime.combine(day, time(16, 0), tzinfo=EASTERN)
    now = datetime.now(EASTERN)
    if day == now.date():
        return min(now, session_close)
    return session_close


def _load_outcome_stock_bars(
    alpaca_client: AlpacaClient,
    entries: list[dict[str, object]],
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, list[dict[str, object]]]:
    bars_by_underlying: dict[str, list[dict[str, object]]] = {}
    for underlying in sorted({str(entry["underlying"]) for entry in entries if entry.get("underlying")}):
        try:
            bars_by_underlying[underlying] = alpaca_client.get_stock_bars(
                underlying,
                start=_to_utc_iso(start_dt),
                end=_to_utc_iso(end_dt),
                timeframe="1Min",
                feed=DEFAULT_STOCK_DATA_FEED,
                limit=10000,
            )
        except AlpacaApiError:
            bars_by_underlying[underlying] = []
    return bars_by_underlying


def _outcome_for_entry(
    entry: dict[str, object],
    bars: list[dict[str, object]],
    stock_bars: list[dict[str, object]],
) -> dict[str, object]:
    if not bars:
        return {"error": "No option bars found after the recorded buy time."}

    high_bar = max(bars, key=lambda bar: _optional_snapshot_float(bar.get("h")) or float("-inf"))
    low_bar = min(bars, key=lambda bar: _optional_snapshot_float(bar.get("l")) or float("inf"))
    high_price = _optional_snapshot_float(high_bar.get("h"))
    low_price = _optional_snapshot_float(low_bar.get("l"))
    entry_price = entry.get("entry_price")
    went_up = high_price is not None and isinstance(entry_price, float) and high_price > entry_price

    high_time = _bar_datetime(high_bar)
    low_time = _bar_datetime(low_bar)
    return {
        "high": high_price,
        "high_time": high_time.isoformat() if high_time else None,
        "high_greeks": _estimate_outcome_greeks(entry, high_price, high_time, stock_bars),
        "low": low_price,
        "low_time": low_time.isoformat() if low_time else None,
        "low_greeks": _estimate_outcome_greeks(entry, low_price, low_time, stock_bars),
        "went_up": went_up,
        "source": "alpaca option bars",
    }


def _fallback_outcome_for_entry(entry: dict[str, object], option_bars_error: str | None) -> dict[str, object]:
    path = entry.get("fallback_path")
    path = path if isinstance(path, list) else []
    prices = [price for price in path if isinstance(price, float)]
    if not prices:
        return {"error": option_bars_error or "No option bars found after the recorded buy time."}

    high_price = max(prices)
    low_price = min(prices)
    entry_price = entry.get("entry_price")
    went_up = high_price is not None and isinstance(entry_price, float) and high_price > entry_price
    greeks = _fallback_greeks(entry)
    return {
        "high": high_price,
        "high_time": None,
        "high_greeks": greeks,
        "low": low_price,
        "low_time": None,
        "low_greeks": greeks,
        "went_up": went_up,
        "source": "saved intraday path fallback",
    }


def _fallback_greeks(entry: dict[str, object]) -> dict[str, float | bool] | None:
    delta = entry.get("fallback_delta")
    gamma = entry.get("fallback_gamma")
    iv = entry.get("entry_iv")
    if not isinstance(delta, float) and not isinstance(gamma, float) and not isinstance(iv, float):
        return None
    return {
        "delta": delta if isinstance(delta, float) else None,
        "gamma": gamma if isinstance(gamma, float) else None,
        "implied_volatility": iv if isinstance(iv, float) else None,
        "estimated": True,
    }


def _estimate_outcome_greeks(
    entry: dict[str, object],
    option_price: float | None,
    as_of: datetime | None,
    stock_bars: list[dict[str, object]],
) -> dict[str, float | bool] | None:
    if option_price is None or as_of is None:
        return None
    spot = _spot_at_or_before(stock_bars, as_of) or entry.get("entry_spot")
    strike = entry.get("strike_price")
    expiration_date = str(entry.get("expiration_date") or "")
    contract_type = str(entry.get("contract_type") or "")
    if not isinstance(spot, float) or not isinstance(strike, float):
        return None
    years = _years_to_expiration_at(expiration_date, as_of)
    if years is None or years <= 0:
        return None
    volatility = _solve_implied_volatility(
        contract_type=contract_type,
        spot=spot,
        strike=strike,
        years=years,
        option_mid=option_price,
    )
    if volatility is None or volatility <= 0:
        entry_iv = entry.get("entry_iv")
        volatility = entry_iv if isinstance(entry_iv, float) and entry_iv > 0 else None
    if volatility is None:
        return None
    delta = _black_scholes_delta(contract_type, spot, strike, years, volatility)
    gamma = _black_scholes_gamma(spot, strike, years, volatility)
    if delta is None or gamma is None:
        return None
    return {
        "delta": delta,
        "gamma": gamma,
        "implied_volatility": volatility,
        "estimated": True,
    }


def _years_to_expiration_at(expiration_date: str, as_of: datetime) -> float | None:
    try:
        expiration_day = date.fromisoformat(expiration_date)
    except ValueError:
        return None
    expiration_dt = datetime.combine(expiration_day, time(16, 0), tzinfo=EASTERN)
    seconds = (expiration_dt - as_of.astimezone(EASTERN)).total_seconds()
    return max(seconds, 60) / (365 * 24 * 60 * 60)


def _spot_at_or_before(stock_bars: list[dict[str, object]], as_of: datetime) -> float | None:
    best_time: datetime | None = None
    best_close: float | None = None
    for bar in stock_bars:
        if not isinstance(bar, dict):
            continue
        bar_time = _bar_datetime(bar)
        close = _optional_snapshot_float(bar.get("c"))
        if bar_time is None or close is None or bar_time > as_of:
            continue
        if best_time is None or bar_time > best_time:
            best_time = bar_time
            best_close = close
    return best_close


def _bar_datetime(bar: dict[str, object]) -> datetime | None:
    timestamp = bar.get("t")
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC).astimezone(EASTERN)
    return parsed.astimezone(EASTERN)


def _underlying_from_option_symbol(symbol: str) -> str:
    prefix = []
    for character in symbol:
        if character.isdigit():
            break
        prefix.append(character)
    return "".join(prefix)


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _technical_as_of(replay_date: str | None, replay_time: str | None) -> datetime:
    if replay_date and replay_time:
        hour_raw, minute_raw, *second_parts = replay_time.split(":")
        second_raw = second_parts[0] if second_parts else "0"
        return datetime.combine(
            date.fromisoformat(replay_date),
            time(int(hour_raw), int(minute_raw), int(second_raw)),
            tzinfo=EASTERN,
        )
    return datetime.now(EASTERN)


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _option_price_from_snapshot(snapshot: object) -> dict[str, float | None]:
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    quote = snapshot.get("latestQuote") if isinstance(snapshot, dict) else None
    quote = quote if isinstance(quote, dict) else {}
    trade = snapshot.get("latestTrade") if isinstance(snapshot, dict) else None
    trade = trade if isinstance(trade, dict) else {}

    bid = _optional_snapshot_float(quote.get("bp"))
    ask = _optional_snapshot_float(quote.get("ap"))
    last = _optional_snapshot_float(trade.get("p"))
    mid = None
    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2
    elif last is not None and last > 0:
        mid = last

    return {
        "bid": bid,
        "ask": ask,
        "last": last,
        "mid": mid,
    }


def _optional_snapshot_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{value!r} must be a number.") from exc


if __name__ == "__main__":
    run_server()
