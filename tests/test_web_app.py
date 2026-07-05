import json
import unittest
from io import BytesIO
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from trading_bot.web_app import TradingBotWebHandler


class WebAppTests(unittest.TestCase):
    def test_handle_analyze_returns_analysis_json(self):
        handler = _handler()
        classic_major_levels = MagicMock()
        state_major_levels = MagicMock()
        classic_max_change = MagicMock()
        state_max_change = MagicMock()
        analysis = MagicMock()
        analysis.as_dict.return_value = {"ticker": "SPX", "bias": "neutral-bullish"}

        client = MagicMock()
        client.get_gex_major_levels.return_value = classic_major_levels
        client.get_state_gex_major_levels.return_value = state_major_levels
        client.get_gex_max_change.return_value = classic_max_change
        client.get_state_gex_max_change.return_value = state_max_change

        with patch("trading_bot.web_app.Settings.from_env", return_value=MagicMock()):
            with patch("trading_bot.web_app.GexClient", return_value=client):
                with patch("trading_bot.web_app.analyze_gex", return_value=analysis) as analyze_mock:
                    handler._handle_analyze("ticker=spx&period=zero")

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(
            json.loads(handler.body.decode("utf-8")),
            {
                "ticker": "SPX",
                "bias": "neutral-bullish",
            },
        )
        client.get_gex_major_levels.assert_called_once_with("SPX", "zero")
        client.get_state_gex_major_levels.assert_called_once_with("SPX", "zero")
        client.get_gex_max_change.assert_called_once_with("SPX", "zero")
        client.get_state_gex_max_change.assert_called_once_with("SPX", "zero")
        analyze_mock.assert_called_once_with(
            period="zero",
            classic_major_levels=classic_major_levels,
            state_major_levels=state_major_levels,
            classic_max_change=classic_max_change,
            state_max_change=state_max_change,
        )

    def test_handle_analyze_rejects_bad_period(self):
        handler = _handler()

        handler._handle_analyze("ticker=spx&period=bad")

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("period", json.loads(handler.body.decode("utf-8"))["error"])

    def test_handle_alpaca_account_returns_account_json(self):
        handler = _handler()
        client = MagicMock()
        client.get_account.return_value = {"status": "ACTIVE", "cash": "100000"}

        with patch("trading_bot.web_app.AlpacaSettings.from_env", return_value=MagicMock()):
            with patch("trading_bot.web_app.AlpacaClient", return_value=client):
                handler._handle_alpaca_account()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(json.loads(handler.body.decode("utf-8"))["status"], "ACTIVE")
        client.get_account.assert_called_once_with()

    def test_handle_submit_alpaca_order_posts_order(self):
        body = json.dumps(
            {
                "symbol": "spy",
                "side": "buy",
                "qty": 1,
                "type": "market",
                "time_in_force": "day",
            }
        ).encode("utf-8")
        handler = _handler(body)
        client = MagicMock()
        client.submit_order.return_value = {"symbol": "SPY", "status": "accepted"}

        with patch("trading_bot.web_app.AlpacaSettings.from_env", return_value=MagicMock()):
            with patch("trading_bot.web_app.AlpacaClient", return_value=client):
                handler._handle_submit_alpaca_order()

        self.assertEqual(handler.status, HTTPStatus.CREATED)
        self.assertEqual(json.loads(handler.body.decode("utf-8"))["status"], "accepted")
        order = client.submit_order.call_args.args[0]
        self.assertEqual(order.symbol, "spy")
        self.assertEqual(order.side, "buy")
        self.assertEqual(order.qty, 1.0)

    def test_handle_option_recommendation_returns_json(self):
        handler = _handler()
        analysis = MagicMock()
        recommendation = MagicMock()
        recommendation.as_dict.return_value = {"ticker": "AAPL", "candidates": []}

        with patch("trading_bot.web_app._analyze_ticker", return_value=analysis) as analyze_mock:
            with patch("trading_bot.web_app._alpaca_client", return_value=MagicMock()) as alpaca_mock:
                with patch("trading_bot.web_app.recommend_option_contracts", return_value=recommendation) as recommend_mock:
                    handler._handle_option_recommendation("ticker=aapl&period=zero&limit=3")

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(json.loads(handler.body.decode("utf-8"))["ticker"], "AAPL")
        analyze_mock.assert_called_once_with("AAPL", "zero")
        alpaca_mock.assert_called_once_with()
        self.assertEqual(recommend_mock.call_args.kwargs["max_candidates"], 3)

    def test_handle_option_replay_returns_json(self):
        handler = _handler()
        analysis = MagicMock()
        alpaca = MagicMock()
        recommendation = MagicMock()
        replay = MagicMock()
        replay.as_dict.return_value = {"date": "2026-07-02", "candidates": []}

        with patch("trading_bot.web_app._analyze_ticker", return_value=analysis) as analyze_mock:
            with patch("trading_bot.web_app._alpaca_client", return_value=alpaca):
                with patch("trading_bot.web_app.recommend_option_contracts", return_value=recommendation):
                    with patch("trading_bot.web_app.replay_option_recommendation", return_value=replay) as replay_mock:
                        handler._handle_option_replay("ticker=aapl&period=zero&date=2026-07-02&time=10:45:30")

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(json.loads(handler.body.decode("utf-8"))["date"], "2026-07-02")
        analyze_mock.assert_called_once_with("AAPL", "zero", replay_date="2026-07-02", replay_time="10:45:30")
        replay_mock.assert_called_once_with(
            recommendation=recommendation,
            alpaca_client=alpaca,
            replay_date="2026-07-02",
            replay_time="10:45:30",
        )

def _handler(body: bytes = b""):
    handler = object.__new__(TradingBotWebHandler)
    handler.status = None
    handler.body = b""
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)

    def send_response(status):
        handler.status = status

    def send_header(_name, _value):
        return None

    def end_headers():
        return None

    class Writer:
        def write(self, body):
            handler.body += body

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    handler.wfile = Writer()
    return handler


if __name__ == "__main__":
    unittest.main()
