"""Local web UI for trading_bot."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from trading_bot.alpaca_client import AlpacaApiError, AlpacaClient, PaperOrderRequest
from trading_bot.analysis import analyze_gex
from trading_bot.config import AlpacaSettings, Settings
from trading_bot.gex_client import AGGREGATION_PERIODS, GexApiError, GexClient
from trading_bot.options_analysis import recommend_option_contracts
from trading_bot.options_replay import replay_option_recommendation


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_DIR = Path(__file__).parent / "static"


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

            recommendation = recommend_option_contracts(
                gex_analysis=_analyze_ticker(ticker, period),
                alpaca_client=_alpaca_client(),
                max_expiration_days=int(max_expiration_days_raw),
                max_candidates=int(limit_raw),
            )
        except (AlpacaApiError, GexApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_json(recommendation.as_dict())

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
            recommendation = recommend_option_contracts(
                gex_analysis=_analyze_ticker(ticker, period, replay_date=replay_date, replay_time=replay_time),
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

        self._send_json(replay.as_dict())

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
        )

    return analyze_gex(
        period=period,
        classic_major_levels=client.get_gex_major_levels(ticker, period),
        state_major_levels=client.get_state_gex_major_levels(ticker, period),
        classic_max_change=client.get_gex_max_change(ticker, period),
        state_max_change=client.get_state_gex_max_change(ticker, period),
    )


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{value!r} must be a number.") from exc


if __name__ == "__main__":
    run_server()
