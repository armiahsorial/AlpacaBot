"""Local web UI for trading_bot."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlparse

from trading_bot.alpaca_client import AlpacaApiError, AlpacaClient, PaperOrderRequest
from trading_bot.analysis import analyze_gex
from trading_bot.config import AlpacaSettings, Settings
from trading_bot.gex_client import (
    AGGREGATION_PERIODS,
    GexApiError,
    GexClient,
    historical_gex_inputs_from_rows,
    historical_state_greek_flow_from_rows,
)
from trading_bot.market_data import MarketDataClient, MarketDataError, create_market_data_client
from trading_bot.options_analysis import _black_scholes_delta, _black_scholes_gamma, _solve_implied_volatility, recommend_option_contracts
from trading_bot.options_replay import replay_option_recommendation
from trading_bot.storage import TradingBotStorage
from trading_bot.technicals import StockTechnicals, calculate_stock_technicals


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_DIR = Path(__file__).parent / "static"
EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
DEFAULT_STOCK_DATA_FEED = "iex"
MAX_OPTION_MARK_SPREAD_RATIO = 0.50
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

        if parsed_url.path == "/api/options/stream-prices":
            self._handle_option_stream_prices(parsed_url.query)
            return

        if parsed_url.path == "/api/options/replay":
            self._handle_option_replay(parsed_url.query)
            return

        if parsed_url.path == "/api/options/replay/validate":
            self._handle_option_replay_validate(parsed_url.query)
            return

        if parsed_url.path == "/api/options/replay/prefetch":
            self._handle_option_replay_prefetch(parsed_url.query)
            return

        if parsed_url.path == "/api/storage/snapshot":
            self._handle_storage_snapshot()
            return

        if parsed_url.path == "/api/storage/history":
            self._handle_storage_history(parsed_url.query)
            return

        if parsed_url.path == "/api/cache/status":
            self._handle_cache_status(parsed_url.query)
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

        if parsed_url.path == "/api/storage/sync":
            self._handle_storage_sync()
            return

        if parsed_url.path == "/api/storage/delete-day":
            self._handle_storage_delete_day()
            return

        if parsed_url.path == "/api/cache/day":
            self._handle_cache_day()
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
                greek_flow=_live_greek_flow(client, ticker, period),
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
        max_contract_cost_raw = params.get("max_contract_cost", [""])[0].strip()

        try:
            if period not in AGGREGATION_PERIODS:
                allowed = ", ".join(AGGREGATION_PERIODS)
                raise ValueError(f"period must be one of: {allowed}.")
            max_contract_cost = float(max_contract_cost_raw) if max_contract_cost_raw else None
            if max_contract_cost is not None and max_contract_cost <= 0:
                raise ValueError("max_contract_cost must be greater than zero.")

            analysis = _analyze_ticker(ticker, period)
            recommendation = recommend_option_contracts(
                gex_analysis=analysis,
                alpaca_client=_market_data_client(),
                max_expiration_days=int(max_expiration_days_raw),
                max_candidates=int(limit_raw),
                max_contract_cost=max_contract_cost,
            )
        except (MarketDataError, GexApiError, ValueError) as exc:
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
            replay_date = params.get("date", [""])[0].strip()
            replay_time = params.get("time", [""])[0].strip()
            if replay_date and replay_time:
                self._send_json({
                    "prices": _historical_option_prices(
                        _market_data_client(), symbols, replay_date, replay_time, option_bar_cache=_storage()
                    )
                })
                return
            snapshots = _market_data_client().get_option_snapshots(symbols)
        except (MarketDataError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        prices = {
            symbol: _option_price_from_snapshot(snapshots.get(symbol, {}))
            for symbol in symbols
        }
        self._send_json({"prices": prices})

    def _handle_option_stream_prices(self, query: str) -> None:
        params = parse_qs(query)
        symbols = [
            symbol.strip().upper()
            for symbol in params.get("symbols", [""])[0].split(",")
            if symbol.strip()
        ]
        try:
            if not symbols:
                raise ValueError("symbols are required.")
            if len(symbols) > 10:
                raise ValueError("The streaming ledger supports at most 10 option symbols.")
            client = _market_data_client()
            stream_method = getattr(client, "get_streaming_option_snapshots", None)
            if stream_method is None:
                self._send_json(
                    {"error": "One-second marks require Databento live streaming."},
                    status=HTTPStatus.CONFLICT,
                )
                return
            snapshots = stream_method(symbols)
        except (MarketDataError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        prices = {
            symbol: _option_price_from_snapshot(snapshots.get(symbol, {}))
            for symbol in symbols
        }
        self._send_json({"prices": prices, "streaming": True})

    def _handle_option_replay_prefetch(self, query: str) -> None:
        self._send_json(
            {"error": "Historical prefetch is disabled. Use Cache Day once after the market closes."},
            status=HTTPStatus.GONE,
        )

    def _handle_option_replay(self, query: str) -> None:
        params = parse_qs(query)
        ticker = params.get("ticker", ["AAPL"])[0].strip().upper()
        period = params.get("period", ["zero"])[0].strip().lower()
        replay_date = params.get("date", [""])[0].strip()
        replay_time = params.get("time", ["15:59"])[0].strip()
        max_expiration_days_raw = params.get("max_expiration_days", ["14"])[0]
        limit_raw = params.get("limit", ["5"])[0]
        max_contract_cost_raw = params.get("max_contract_cost", [""])[0].strip()
        # Replay is deliberately SQLite-only. Cache Day is the sole path that
        # downloads completed-session data from market/GEX providers.
        local_only = True

        try:
            if not replay_date:
                raise ValueError("date is required.")
            if period not in AGGREGATION_PERIODS:
                allowed = ", ".join(AGGREGATION_PERIODS)
                raise ValueError(f"period must be one of: {allowed}.")
            max_contract_cost = float(max_contract_cost_raw) if max_contract_cost_raw else None
            if max_contract_cost is not None and max_contract_cost <= 0:
                raise ValueError("max_contract_cost must be greater than zero.")
            requested_limit = int(limit_raw)
            if local_only:
                payload = _cached_replay_payload(
                    storage=_storage(),
                    ticker=ticker,
                    period=period,
                    replay_date=replay_date,
                    replay_time=replay_time,
                    limit=requested_limit,
                    max_contract_cost=max_contract_cost,
                )
                self._send_json(payload)
                return
            alpaca_client = _market_data_client()
            analysis = _analyze_ticker(ticker, period, replay_date=replay_date, replay_time=replay_time)
            recommendation = recommend_option_contracts(
                gex_analysis=analysis,
                alpaca_client=alpaca_client,
                max_expiration_days=int(max_expiration_days_raw),
                max_candidates=max(requested_limit, 25 if max_contract_cost is not None else requested_limit),
            )
            replay = replay_option_recommendation(
                recommendation=recommendation,
                alpaca_client=alpaca_client,
                replay_date=replay_date,
                replay_time=replay_time,
            )
        except (MarketDataError, GexApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        payload = replay.as_dict()
        if max_contract_cost is not None:
            payload["candidates"] = [
                candidate
                for candidate in payload["candidates"]
                if candidate.get("close") is not None and float(candidate["close"]) * 100 <= max_contract_cost
            ][:requested_limit]
            allowed_symbols = {candidate["symbol"] for candidate in payload["candidates"]}
            payload["recommendation"]["candidates"] = [
                candidate
                for candidate in payload["recommendation"].get("candidates", [])
                if candidate.get("symbol") in allowed_symbols
            ]
            if not payload["candidates"]:
                payload["warning"] = (
                    f"No historical option candidate was priced at or below ${max_contract_cost:,.0f} per contract."
                )
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
            rows = _storage().gex_rows(replay_date, ticker, period)
        except (OSError, sqlite3.Error, ValueError) as exc:
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

        valid = set(rows) == {"classic", "state"}
        self._send_json({
            "valid": valid,
            "ticker": ticker,
            "period": period,
            "date": replay_date,
            "classic_available": "classic" in rows,
            "state_available": "state" in rows,
            "source": "SQLite",
        })

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
            if len(entries) > 1000:
                raise ValueError("At most 1,000 option entries can be evaluated at once.")
            local_only = bool(payload.get("local_only"))
            outcomes = _option_outcomes(
                _market_data_client(),
                entries,
                option_bar_cache=_storage(),
                allow_remote=not local_only,
            )
            self._send_json({"outcomes": outcomes})
        except (MarketDataError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_storage_snapshot(self) -> None:
        try:
            self._send_json(_storage().snapshot())
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._send_json({"error": f"Database read failed: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_storage_history(self, query: str) -> None:
        try:
            params = parse_qs(query)
            day = params.get("date", [""])[0].strip()
            self._send_json(_storage().history_for_day(day))
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._send_json({"error": f"Database history read failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _handle_storage_sync(self) -> None:
        try:
            payload = self._read_json_body()
            trade_history = payload.get("trade_history", [])
            paper_ledger = payload.get("paper_ledger", [])
            tracked_tickers = payload.get("tracked_tickers", {})
            if not isinstance(trade_history, list) or not isinstance(paper_ledger, list):
                raise ValueError("trade_history and paper_ledger must be arrays.")
            if not isinstance(tracked_tickers, dict):
                raise ValueError("tracked_tickers must be an object.")
            counts = _storage().sync(
                trade_history=trade_history,
                paper_ledger=paper_ledger,
                tracked_tickers=tracked_tickers,
            )
            self._send_json({"saved": counts, "database_path": str(_storage().path)})
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._send_json({"error": f"Database write failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _handle_storage_delete_day(self) -> None:
        try:
            payload = self._read_json_body()
            record_type = str(payload.get("record_type") or "")
            day = str(payload.get("day") or "")
            deleted = _storage().delete_day(record_type, day)
            self._send_json({"deleted": deleted, "record_type": record_type, "day": day})
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._send_json({"error": f"Database delete failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _handle_cache_status(self, query: str) -> None:
        try:
            params = parse_qs(query)
            day = params.get("date", [""])[0].strip()
            period = params.get("period", [""])[0].strip().lower() or None
            provider = str(getattr(_market_data_client(), "provider_name", "market-data"))
            rows = _storage().cache_status(day, period=period, provider=provider)
            self._send_json({"date": day, "provider": provider, "caches": rows})
        except (OSError, sqlite3.Error, ValueError) as exc:
            self._send_json({"error": f"Cache status read failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _handle_cache_day(self) -> None:
        try:
            payload = self._read_json_body()
            day = str(payload.get("date") or "").strip()
            period = str(payload.get("period") or "zero").strip().lower()
            tickers = payload.get("tickers")
            if tickers is not None and not isinstance(tickers, list):
                raise ValueError("tickers must be an array when provided.")
            result = _cache_completed_day(
                storage=_storage(),
                market_client=_market_data_client(),
                gex_client=GexClient(Settings.from_env()),
                replay_date=day,
                period=period,
                tickers=[str(value) for value in tickers] if tickers else None,
                force=bool(payload.get("force")),
            )
            self._send_json(result)
        except (MarketDataError, GexApiError, OSError, sqlite3.Error, ValueError) as exc:
            self._send_json({"error": f"Day cache failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self._send_json({"error": "File not found."}, status=HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

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


@lru_cache(maxsize=1)
def _storage() -> TradingBotStorage:
    return TradingBotStorage()


@lru_cache(maxsize=1)
def _market_data_client() -> MarketDataClient:
    return create_market_data_client()


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
            greek_flow=None,
        )

    return analyze_gex(
        period=period,
        classic_major_levels=client.get_gex_major_levels(ticker, period),
        state_major_levels=client.get_state_gex_major_levels(ticker, period),
        classic_max_change=client.get_gex_max_change(ticker, period),
        state_max_change=client.get_state_gex_max_change(ticker, period),
        technicals=technicals,
        greek_flow=_live_greek_flow(client, ticker, period),
    )


def _live_greek_flow(client: GexClient, ticker: str, period: str):
    try:
        return client.get_state_greek_flow(ticker, period)
    except GexApiError:
        return None


def _stock_technicals(ticker: str, replay_date: str | None = None, replay_time: str | None = None) -> StockTechnicals:
    alpaca_client = _market_data_client()
    stock_feed = None if getattr(alpaca_client, "provider_name", "alpaca") == "databento" else DEFAULT_STOCK_DATA_FEED
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
        feed=stock_feed,
        limit=10000,
    )
    daily_bars = alpaca_client.get_stock_bars(
        symbol,
        start=daily_start.isoformat(),
        end=daily_end.isoformat(),
        timeframe="1Day",
        feed=stock_feed,
        limit=300,
    )
    return calculate_stock_technicals(
        symbol=symbol,
        as_of=as_of.isoformat(),
        minute_bars=minute_bars,
        daily_bars=daily_bars,
    )


def _cache_completed_day(
    *,
    storage: TradingBotStorage,
    market_client: MarketDataClient,
    gex_client: GexClient,
    replay_date: str,
    period: str,
    tickers: list[str] | None,
    force: bool,
) -> dict[str, object]:
    if period not in AGGREGATION_PERIODS:
        raise ValueError(f"period must be one of: {', '.join(AGGREGATION_PERIODS)}.")
    session_day = date.fromisoformat(replay_date)
    session_close = datetime.combine(session_day, time(16, 0), tzinfo=EASTERN)
    if datetime.now(EASTERN) <= session_close:
        raise ValueError("The selected market session must be complete before it can be cached.")

    history = storage.history_for_day(replay_date)["trade_history"]
    requested = {str(value).strip().upper() for value in (tickers or []) if str(value).strip()}
    available = sorted({
        str(row.get("ticker") or row.get("underlying") or "").strip().upper()
        for row in history
        if isinstance(row, dict)
    } - {""})
    selected = sorted(requested.intersection(available)) if requested else available
    if not selected:
        raise ValueError("No recorded contracts were found for the selected date and tickers.")

    provider = str(getattr(market_client, "provider_name", "market-data"))
    results: list[dict[str, object]] = []
    for ticker in selected:
        ticker_rows = [
            row for row in history
            if isinstance(row, dict)
            and str(row.get("ticker") or row.get("underlying") or "").strip().upper() == ticker
        ]
        symbols = sorted({str(row.get("symbol") or "").strip().upper() for row in ticker_rows} - {""})
        existing = storage.cache_status(replay_date, period=period, provider=provider)
        already_complete = any(row["ticker"] == ticker and row["status"] == "complete" for row in existing)
        stock_symbol = TECHNICAL_UNDERLYING_OVERRIDES.get(ticker, ticker)
        cached_options = storage.option_bars(provider, replay_date, symbols)
        cached_minute_bars = storage.stock_bars(provider, replay_date, stock_symbol, "1Min")
        cached_daily_bars = storage.stock_bars(provider, replay_date, stock_symbol, "1Day")
        cached_gex_modes = set(storage.gex_rows(replay_date, ticker, period))
        required_gex_modes = {"classic", "state"} if period == "full" else {"classic", "state", "vanna", "charm"}
        cache_is_complete = (
            set(cached_options) == set(symbols)
            and cached_minute_bars is not None
            and cached_daily_bars is not None
            and cached_gex_modes == required_gex_modes
        )
        if already_complete and cache_is_complete and not force:
            results.append({"ticker": ticker, "status": "complete", "cached": True, "contracts": len(symbols)})
            continue

        detail: dict[str, object] = {"contracts": symbols, "errors": []}
        storage.save_cache_status(
            replay_date, ticker, period, provider,
            status="building", option_contract_count=len(symbols), detail=detail,
        )
        try:
            market_open = datetime.combine(session_day, time(9, 30), tzinfo=EASTERN)
            cached_options = {} if force else cached_options
            missing_symbols = [symbol for symbol in symbols if symbol not in cached_options]
            for index in range(0, len(missing_symbols), 50):
                batch = missing_symbols[index:index + 50]
                fetched = market_client.get_option_bars(
                    batch,
                    start=_to_utc_iso(market_open),
                    end=_to_utc_iso(session_close),
                    timeframe="1Min",
                    limit=10000,
                )
                storage.save_option_bars(
                    provider,
                    replay_date,
                    {symbol: fetched.get(symbol, []) for symbol in batch},
                )

            stock_feed = None if provider.lower() == "databento" else DEFAULT_STOCK_DATA_FEED
            minute_bars = None if force else cached_minute_bars
            if minute_bars is None:
                minute_bars = market_client.get_stock_bars(
                    stock_symbol,
                    start=_to_utc_iso(market_open),
                    end=_to_utc_iso(session_close),
                    timeframe="1Min",
                    feed=stock_feed,
                    limit=10000,
                )
                storage.save_stock_bars(provider, replay_date, stock_symbol, "1Min", minute_bars)

            daily_bars = None if force else cached_daily_bars
            if daily_bars is None:
                daily_bars = market_client.get_stock_bars(
                    stock_symbol,
                    start=(session_day - timedelta(days=360)).isoformat(),
                    end=session_day.isoformat(),
                    timeframe="1Day",
                    feed=stock_feed,
                    limit=300,
                )
                storage.save_stock_bars(provider, replay_date, stock_symbol, "1Day", daily_bars)

            if force or not {"classic", "state"}.issubset(cached_gex_modes):
                gex_client.prefetch_historical_gex_date(ticker, period, replay_date)
            gex_rows = gex_client.cached_historical_gex_rows(ticker, period, replay_date)
            if period != "full" and (force or not {"vanna", "charm"}.issubset(cached_gex_modes)):
                gex_client.prefetch_historical_state_greeks_date(ticker, period, replay_date)
            if period != "full":
                gex_rows.update(gex_client.cached_historical_state_greek_rows(ticker, period, replay_date))
            storage.save_gex_rows(replay_date, ticker, period, gex_rows)

            detail.update({
                "option_bars": len(symbols),
                "stock_symbol": stock_symbol,
                "stock_minute_bars": len(minute_bars),
                "stock_daily_bars": len(daily_bars),
                "gex_modes": sorted(required_gex_modes),
            })
            storage.save_cache_status(
                replay_date, ticker, period, provider,
                status="complete", option_contract_count=len(symbols), detail=detail,
            )
            results.append({"ticker": ticker, "status": "complete", "cached": False, "contracts": len(symbols)})
        except (MarketDataError, GexApiError, OSError, sqlite3.Error, ValueError) as exc:
            detail["errors"] = [str(exc)]
            storage.save_cache_status(
                replay_date, ticker, period, provider,
                status="error", option_contract_count=len(symbols), detail=detail,
            )
            results.append({"ticker": ticker, "status": "error", "error": str(exc), "contracts": len(symbols)})

    return {
        "date": replay_date,
        "period": period,
        "provider": provider,
        "results": results,
        "complete": all(row["status"] == "complete" for row in results),
    }


def _cached_stock_technicals(
    storage: TradingBotStorage,
    provider: str,
    ticker: str,
    replay_date: str,
    replay_time: str,
) -> StockTechnicals:
    symbol = TECHNICAL_UNDERLYING_OVERRIDES.get(ticker, ticker)
    minute_bars = storage.stock_bars(provider, replay_date, symbol, "1Min")
    daily_bars = storage.stock_bars(provider, replay_date, symbol, "1Day")
    if minute_bars is None or daily_bars is None:
        raise ValueError(f"{ticker} stock bars for {replay_date} are not fully cached.")
    as_of = _technical_as_of(replay_date, replay_time)
    visible_minutes = [
        bar for bar in minute_bars
        if not isinstance(bar, dict) or _bar_datetime(bar) is None or _bar_datetime(bar) <= as_of
    ]
    return calculate_stock_technicals(
        symbol=symbol,
        as_of=as_of.isoformat(),
        minute_bars=visible_minutes,
        daily_bars=daily_bars,
    )


def _cached_replay_payload(
    *,
    storage: TradingBotStorage,
    ticker: str,
    period: str,
    replay_date: str,
    replay_time: str,
    limit: int,
    max_contract_cost: float | None,
) -> dict[str, object]:
    provider = str(getattr(_market_data_client(), "provider_name", "market-data"))
    status = storage.cache_status(replay_date, period=period, provider=provider)
    if not any(row["ticker"] == ticker and row["status"] == "complete" for row in status):
        raise ValueError(
            f"{ticker} {replay_date} is not fully cached in SQLite. Use Cache Day after the market closes."
        )
    selected_dt = _technical_as_of(replay_date, replay_time)
    rows_by_mode = storage.gex_rows_at(
        replay_date,
        ticker,
        period,
        int(selected_dt.timestamp()),
    )
    classic, state, classic_change, state_change = historical_gex_inputs_from_rows(
        rows_by_mode, replay_date, replay_time
    )
    technicals = _cached_stock_technicals(storage, provider, ticker, replay_date, replay_time)
    analysis = analyze_gex(
        period=period,
        classic_major_levels=classic,
        state_major_levels=state,
        classic_max_change=classic_change,
        state_max_change=state_change,
        technicals=technicals,
        greek_flow=historical_state_greek_flow_from_rows(
            rows_by_mode,
            replay_date,
            replay_time,
            period=period,
        ),
    )

    history = [
        row for row in storage.history_for_day(replay_date)["trade_history"]
        if isinstance(row, dict)
        and str(row.get("ticker") or row.get("underlying") or "").strip().upper() == ticker
        and (_history_record_datetime(row) is None or _history_record_datetime(row) <= selected_dt)
    ]
    history.sort(key=lambda row: _history_record_datetime(row) or datetime.min.replace(tzinfo=EASTERN), reverse=True)
    latest_minute = (_history_record_datetime(history[0]).replace(second=0, microsecond=0) if history else None)
    picks = [
        row for row in history
        if latest_minute is not None
        and _history_record_datetime(row) is not None
        and _history_record_datetime(row).replace(second=0, microsecond=0) == latest_minute
    ][:max(1, limit)]

    symbols = [str(row.get("symbol") or "").upper() for row in picks]
    bars_by_symbol = storage.option_bars(provider, replay_date, symbols)
    candidates: list[dict[str, object]] = []
    recommendation_candidates: list[dict[str, object]] = []
    for row in picks:
        symbol = str(row.get("symbol") or "").upper()
        bars = [
            bar for bar in bars_by_symbol.get(symbol, [])
            if isinstance(bar, dict) and (_bar_datetime(bar) is None or _bar_datetime(bar) <= selected_dt)
        ]
        latest = max(bars, key=lambda bar: _bar_datetime(bar) or datetime.min.replace(tzinfo=EASTERN)) if bars else {}
        close = _optional_snapshot_float(latest.get("c"))
        if max_contract_cost is not None and close is not None and close * 100 > max_contract_cost:
            continue
        contract = row.get("decisionSnapshot", {}).get("contract", {}) if isinstance(row.get("decisionSnapshot"), dict) else {}
        base = {
            "symbol": symbol,
            "expiration_date": row.get("expirationDate") or contract.get("expiration"),
            "strike_price": row.get("strikePrice") or contract.get("strike"),
            "contract_type": row.get("contractType") or row.get("side") or contract.get("type"),
            "delta": contract.get("delta") or (row.get("entryGreeks") or {}).get("delta"),
            "gamma": contract.get("gamma") or (row.get("entryGreeks") or {}).get("gamma"),
            "implied_volatility": contract.get("impliedVolatility") or (row.get("entryGreeks") or {}).get("implied_volatility"),
            "score": row.get("score"),
        }
        recommendation_candidates.append({
            **base,
            "bid": contract.get("bid"), "ask": contract.get("ask"), "mid": close,
            "spread": None, "spread_pct": contract.get("spreadPercent"),
            "open_interest": contract.get("openInterest"), "reasons": [], "price_path": [],
        })
        candidates.append({
            **base,
            "last_time": latest.get("t"),
            "open": _optional_snapshot_float(latest.get("o")),
            "high": _optional_snapshot_float(latest.get("h")),
            "low": _optional_snapshot_float(latest.get("l")),
            "close": close,
            "volume": _optional_snapshot_float(latest.get("v")),
            "day_change_pct": None,
            "replay_score": row.get("score"),
            "price_path": [
                value for value in (_optional_snapshot_float(bar.get("c")) for bar in bars) if value is not None
            ],
        })

    permission = str(picks[0].get("permission") if picks else analysis.trade_permission)
    recommendation = {
        "ticker": ticker,
        "underlying_symbol": ticker,
        "period": period,
        "gex_timestamp": analysis.timestamp,
        "gex_spot": analysis.spot,
        "bias": analysis.bias,
        "contract_type": picks[0].get("contractType") if picks else None,
        "target_level": None,
        "trade_permission": permission,
        "recommendation": "Cached recorded candidates nearest the selected replay minute.",
        "candidates": recommendation_candidates,
        "warnings": [],
    }
    return {
        "date": replay_date,
        "selected_time": replay_time,
        "recommendation": recommendation,
        "candidates": candidates,
        "warning": None if candidates else "No recorded candidates existed by this replay time.",
        "analysis": analysis.as_dict(),
        "cached_replay": True,
    }


def _history_record_datetime(row: dict[str, object]) -> datetime | None:
    timestamp = row.get("timestamp")
    value = timestamp.get("iso") if isinstance(timestamp, dict) else row.get("timestamp_iso")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=EASTERN) if parsed.tzinfo is None else parsed.astimezone(EASTERN)


def _option_outcomes(
    alpaca_client: MarketDataClient,
    raw_entries: list[object],
    *,
    option_bar_cache: TradingBotStorage | None = None,
    allow_remote: bool = True,
) -> dict[str, dict[str, object]]:
    entries = [_normalize_option_outcome_entry(entry) for entry in raw_entries]
    entries = [entry for entry in entries if entry is not None]
    if not entries:
        raise ValueError("entries did not include any usable option symbols.")

    outcomes: dict[str, dict[str, object]] = {}
    for outcome_date in sorted({entry["date"] for entry in entries}):
        date_entries = [entry for entry in entries if entry["date"] == outcome_date]
        symbols = sorted({entry["symbol"] for entry in date_entries})
        start_dt = min(entry["start_dt"] for entry in date_entries)
        end_dt = max(entry["end_dt"] for entry in date_entries)
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(minutes=1)

        provider = str(getattr(alpaca_client, "provider_name", "market-data"))
        session_day = date.fromisoformat(outcome_date)
        session_close = datetime.combine(session_day, time(16, 0), tzinfo=EASTERN)
        is_completed_session = datetime.now(EASTERN) >= session_close
        allow_remote_for_date = allow_remote and not is_completed_session
        use_cached_bars = option_bar_cache is not None and (
            is_completed_session or not allow_remote_for_date
        )
        option_bars = (
            option_bar_cache.option_bars(provider, outcome_date, symbols)
            if use_cached_bars
            else {}
        )
        missing_symbols = [symbol for symbol in symbols if symbol not in option_bars]
        option_bars_error = None
        if missing_symbols and allow_remote_for_date:
            fetch_start = start_dt
            fetch_end = end_dt
            if is_completed_session:
                fetch_start = datetime.combine(session_day, time(9, 30), tzinfo=EASTERN)
                fetch_end = datetime.combine(session_day, time(16, 0), tzinfo=EASTERN)
            try:
                fetched_bars = alpaca_client.get_option_bars(
                    missing_symbols,
                    start=_to_utc_iso(fetch_start),
                    end=_to_utc_iso(fetch_end),
                    timeframe="1Min",
                )
                option_bars.update(fetched_bars)
                if option_bar_cache is not None and is_completed_session:
                    option_bar_cache.save_option_bars(provider, outcome_date, fetched_bars)
            except MarketDataError as exc:
                option_bars_error = str(exc)
        stock_bars_by_underlying = _load_outcome_stock_bars(
            alpaca_client,
            date_entries,
            start_dt,
            end_dt,
            stock_bar_cache=option_bar_cache,
            outcome_date=outcome_date,
            allow_remote=allow_remote_for_date,
        )
        gex_spots_by_underlying = {
            underlying: option_bar_cache.gex_spot_rows(outcome_date, underlying)
            for underlying in sorted({str(entry["underlying"]) for entry in date_entries})
            if option_bar_cache is not None and underlying in TECHNICAL_UNDERLYING_OVERRIDES
        }

        for entry in date_entries:
            bars = [
                bar
                for bar in option_bars.get(entry["symbol"], [])
                if isinstance(bar, dict) and (
                    _bar_datetime(bar) is None or
                    entry["start_dt"] <= _bar_datetime(bar) <= entry["end_dt"]
                )
            ]
            if bars:
                outcomes[entry["id"]] = _outcome_for_entry(
                    entry,
                    bars,
                    stock_bars_by_underlying.get(entry["underlying"], []),
                    gex_spots_by_underlying.get(entry["underlying"], []),
                )
            else:
                symbol_bars = option_bars.get(entry["symbol"])
                if symbol_bars is None:
                    cache_message = (
                        option_bars_error
                        or "Contract is not cached in SQLite. Run Cache Day after the market closes."
                    )
                elif symbol_bars:
                    cache_message = (
                        "Cached in SQLite; no option trade occurred between the recorded buy time "
                        "and the selected replay time."
                    )
                else:
                    cache_message = (
                        "Cached in SQLite; the market-data provider reported no trades for this contract that day."
                    )
                outcomes[entry["id"]] = _fallback_outcome_for_entry(entry, cache_message)

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
    as_of_time = str(entry.get("as_of_time", "")).strip()
    as_of_iso = str(entry.get("as_of_iso", "")).strip()
    replay_end_dt = None
    if as_of_iso:
        try:
            replay_end_dt = datetime.fromisoformat(as_of_iso.replace("Z", "+00:00"))
            if replay_end_dt.tzinfo is None:
                replay_end_dt = replay_end_dt.replace(tzinfo=EASTERN)
            else:
                replay_end_dt = replay_end_dt.astimezone(EASTERN)
        except ValueError:
            replay_end_dt = None
    end_dt = min(
        replay_end_dt or (_technical_as_of(outcome_date or start_dt.date().isoformat(), as_of_time) if as_of_time else _option_outcome_end_dt(outcome_date or start_dt.date().isoformat())),
        _option_outcome_end_dt(outcome_date or start_dt.date().isoformat()),
    )
    underlying = str(entry.get("underlying", "")).strip().upper() or _underlying_from_option_symbol(symbol)
    return {
        "id": str(entry.get("id") or symbol),
        "symbol": symbol,
        "date": outcome_date or start_dt.date().isoformat(),
        "start_dt": start_dt,
        "end_dt": end_dt,
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
    alpaca_client: MarketDataClient,
    entries: list[dict[str, object]],
    start_dt: datetime,
    end_dt: datetime,
    *,
    stock_bar_cache: TradingBotStorage | None = None,
    outcome_date: str = "",
    allow_remote: bool = True,
) -> dict[str, list[dict[str, object]]]:
    bars_by_underlying: dict[str, list[dict[str, object]]] = {}
    provider = str(getattr(alpaca_client, "provider_name", "alpaca"))
    stock_feed = None if provider == "databento" else DEFAULT_STOCK_DATA_FEED
    for underlying in sorted({str(entry["underlying"]) for entry in entries if entry.get("underlying")}):
        symbol = TECHNICAL_UNDERLYING_OVERRIDES.get(underlying, underlying)
        cached = (
            stock_bar_cache.stock_bars(provider, outcome_date, symbol, "1Min")
            if stock_bar_cache is not None and outcome_date
            else None
        )
        if cached is not None:
            bars_by_underlying[underlying] = cached
            continue
        if not allow_remote:
            bars_by_underlying[underlying] = []
            continue
        try:
            bars_by_underlying[underlying] = alpaca_client.get_stock_bars(
                symbol,
                start=_to_utc_iso(start_dt),
                end=_to_utc_iso(end_dt),
                timeframe="1Min",
                feed=stock_feed,
                limit=10000,
            )
        except MarketDataError:
            bars_by_underlying[underlying] = []
    return bars_by_underlying


def _outcome_for_entry(
    entry: dict[str, object],
    bars: list[dict[str, object]],
    stock_bars: list[dict[str, object]],
    gex_spot_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if not bars:
        return {"error": "No option bars found after the recorded buy time."}

    high_bar = max(bars, key=lambda bar: _optional_snapshot_float(bar.get("h")) or float("-inf"))
    low_bar = min(bars, key=lambda bar: _optional_snapshot_float(bar.get("l")) or float("inf"))
    latest_bar = max(
        enumerate(bars),
        key=lambda item: (_bar_datetime(item[1]) or datetime.min.replace(tzinfo=EASTERN), item[0]),
    )[1]
    high_price = _optional_snapshot_float(high_bar.get("h"))
    low_price = _optional_snapshot_float(low_bar.get("l"))
    current_price = _optional_snapshot_float(latest_bar.get("c"))
    entry_price = entry.get("entry_price")
    went_up = high_price is not None and isinstance(entry_price, float) and high_price > entry_price

    high_time = _bar_datetime(high_bar)
    low_time = _bar_datetime(low_bar)
    current_time = _bar_datetime(latest_bar)
    current_age_seconds = (
        max(0, int((entry["end_dt"] - current_time).total_seconds()))
        if current_time is not None
        else None
    )
    return {
        "high": high_price,
        "high_time": high_time.isoformat() if high_time else None,
        "high_greeks": _estimate_outcome_greeks(entry, high_price, high_time, stock_bars, gex_spot_rows),
        "low": low_price,
        "low_time": low_time.isoformat() if low_time else None,
        "low_greeks": _estimate_outcome_greeks(entry, low_price, low_time, stock_bars, gex_spot_rows),
        "current": current_price,
        "current_time": current_time.isoformat() if current_time else None,
        "current_age_seconds": current_age_seconds,
        "current_is_stale": current_age_seconds is not None and current_age_seconds > 120,
        "went_up": went_up,
        "source": "market-data option bars",
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
        "current": prices[-1],
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
    gex_spot_rows: list[dict[str, object]] | None = None,
) -> dict[str, float | bool] | None:
    if option_price is None or as_of is None:
        return None
    spot = _outcome_underlying_spot(entry, as_of, stock_bars, gex_spot_rows or [])
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


def _outcome_underlying_spot(
    entry: dict[str, object],
    as_of: datetime,
    stock_bars: list[dict[str, object]],
    gex_spot_rows: list[dict[str, object]],
) -> float | None:
    underlying = str(entry.get("underlying") or "").upper()
    entry_spot = entry.get("entry_spot")
    if underlying in TECHNICAL_UNDERLYING_OVERRIDES:
        gex_spot = _gex_spot_at_or_before(gex_spot_rows, as_of)
        if gex_spot is not None:
            return gex_spot

        proxy_spot = _spot_at_or_before(stock_bars, as_of)
        entry_proxy_spot = _spot_at_or_before(stock_bars, entry["start_dt"])
        if (
            isinstance(entry_spot, float)
            and proxy_spot is not None
            and entry_proxy_spot is not None
            and entry_proxy_spot > 0
        ):
            return proxy_spot * entry_spot / entry_proxy_spot
        return entry_spot if isinstance(entry_spot, float) else None
    return _spot_at_or_before(stock_bars, as_of) or (entry_spot if isinstance(entry_spot, float) else None)


def _gex_spot_at_or_before(rows: list[dict[str, object]], as_of: datetime) -> float | None:
    target = as_of.timestamp()
    best_timestamp: float | None = None
    best_spot: float | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        timestamp = _optional_snapshot_float(row.get("timestamp"))
        spot = _optional_snapshot_float(row.get("spot"))
        if timestamp is None or spot is None or timestamp > target:
            continue
        if best_timestamp is None or timestamp > best_timestamp:
            best_timestamp = timestamp
            best_spot = spot
    return best_spot


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
        quote_mid = (bid + ask) / 2
        spread_ratio = (ask - bid) / quote_mid
        if spread_ratio <= MAX_OPTION_MARK_SPREAD_RATIO:
            mid = quote_mid
        elif last is not None and last > 0:
            mid = last
    elif last is not None and last > 0:
        mid = last

    return {
        "bid": bid,
        "ask": ask,
        "last": last,
        "mid": mid,
    }


def _historical_option_prices(
    alpaca_client: MarketDataClient,
    symbols: list[str],
    replay_date: str,
    replay_time: str,
    *,
    option_bar_cache: TradingBotStorage | None = None,
) -> dict[str, dict[str, float | str | None]]:
    as_of = _technical_as_of(replay_date, replay_time)
    provider = str(getattr(alpaca_client, "provider_name", "market-data"))
    bars_by_symbol = option_bar_cache.option_bars(provider, replay_date, symbols) if option_bar_cache else {}
    prices: dict[str, dict[str, float | str | None]] = {}
    for symbol in symbols:
        bars = [
            bar for bar in bars_by_symbol.get(symbol, [])
            if isinstance(bar, dict) and (_bar_datetime(bar) is None or _bar_datetime(bar) <= as_of)
        ]
        latest = max(bars, key=lambda bar: _bar_datetime(bar) or datetime.min.replace(tzinfo=EASTERN)) if bars else {}
        close = _optional_snapshot_float(latest.get("c")) if isinstance(latest, dict) else None
        prices[symbol] = {
            "bid": None,
            "ask": None,
            "last": close,
            "mid": close,
            "source": "SQLite historical option bar" if symbol in bars_by_symbol else "not cached in SQLite",
        }
    return prices


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
