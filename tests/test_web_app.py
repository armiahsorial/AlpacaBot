import json
import unittest
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

def _handler():
    handler = object.__new__(TradingBotWebHandler)
    handler.status = None
    handler.body = b""

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
