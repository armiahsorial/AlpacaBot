"""Local web UI for trading_bot."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from trading_bot.analysis import analyze_gex
from trading_bot.config import Settings
from trading_bot.gex_client import AGGREGATION_PERIODS, GexApiError, GexClient


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


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), TradingBotWebHandler)
    print(f"trading_bot web UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
