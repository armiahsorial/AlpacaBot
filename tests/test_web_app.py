import json
import unittest
from io import BytesIO
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from trading_bot.alpaca_client import AlpacaApiError
from trading_bot.web_app import (
    TradingBotWebHandler,
    _historical_option_prices,
    _option_outcomes,
    _stock_technicals,
)


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
        analysis.as_dict.return_value = {"ticker": "AAPL", "bias": "bullish"}
        recommendation = MagicMock()
        recommendation.as_dict.return_value = {"ticker": "AAPL", "candidates": []}

        with patch("trading_bot.web_app._analyze_ticker", return_value=analysis) as analyze_mock:
            with patch("trading_bot.web_app._alpaca_client", return_value=MagicMock()) as alpaca_mock:
                with patch("trading_bot.web_app.recommend_option_contracts", return_value=recommendation) as recommend_mock:
                    handler._handle_option_recommendation(
                        "ticker=aapl&period=zero&limit=3&max_contract_cost=500"
                    )

        self.assertEqual(handler.status, HTTPStatus.OK)
        payload = json.loads(handler.body.decode("utf-8"))
        self.assertEqual(payload["ticker"], "AAPL")
        self.assertEqual(payload["analysis"]["bias"], "bullish")
        analyze_mock.assert_called_once_with("AAPL", "zero")
        alpaca_mock.assert_called_once_with()
        self.assertEqual(recommend_mock.call_args.kwargs["max_candidates"], 3)
        self.assertEqual(recommend_mock.call_args.kwargs["max_contract_cost"], 500)

    def test_handle_option_prices_returns_current_mids(self):
        handler = _handler()
        alpaca = MagicMock()
        alpaca.get_option_snapshots.return_value = {
            "AAPL260710C00310000": {
                "latestQuote": {"bp": 2.4, "ap": 2.6},
                "latestTrade": {"p": 2.55},
            }
        }

        with patch("trading_bot.web_app._alpaca_client", return_value=alpaca):
            handler._handle_option_prices("symbols=AAPL260710C00310000")

        self.assertEqual(handler.status, HTTPStatus.OK)
        payload = json.loads(handler.body.decode("utf-8"))
        self.assertEqual(payload["prices"]["AAPL260710C00310000"]["mid"], 2.5)
        alpaca.get_option_snapshots.assert_called_once_with(["AAPL260710C00310000"])

    def test_handle_option_replay_returns_json(self):
        handler = _handler()
        analysis = MagicMock()
        analysis.as_dict.return_value = {"ticker": "AAPL", "bias": "bearish"}
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
        payload = json.loads(handler.body.decode("utf-8"))
        self.assertEqual(payload["date"], "2026-07-02")
        self.assertEqual(payload["analysis"]["bias"], "bearish")
        analyze_mock.assert_called_once_with("AAPL", "zero", replay_date="2026-07-02", replay_time="10:45:30")
        replay_mock.assert_called_once_with(
            recommendation=recommendation,
            alpaca_client=alpaca,
            replay_date="2026-07-02",
            replay_time="10:45:30",
        )

    def test_stock_technicals_uses_iex_feed_for_alpaca_bars(self):
        alpaca = MagicMock()
        alpaca.get_stock_bars.return_value = []

        with patch("trading_bot.web_app._alpaca_client", return_value=alpaca):
            _stock_technicals("AAPL", replay_date="2026-07-02", replay_time="10:45:30")

        self.assertEqual(alpaca.get_stock_bars.call_count, 2)
        for call in alpaca.get_stock_bars.call_args_list:
            self.assertEqual(call.kwargs["feed"], "iex")

    def test_option_outcomes_returns_high_low_and_estimated_greeks(self):
        alpaca = MagicMock()
        alpaca.get_option_bars.return_value = {
            "AAPL260710C00100000": [
                {"t": "2026-07-10T14:30:00Z", "h": 2.6, "l": 2.1},
                {"t": "2026-07-10T15:00:00Z", "h": 4.2, "l": 3.8},
                {"t": "2026-07-10T16:00:00Z", "h": 1.9, "l": 1.4},
            ]
        }
        alpaca.get_stock_bars.return_value = [
            {"t": "2026-07-10T14:30:00Z", "c": 100.0},
            {"t": "2026-07-10T15:00:00Z", "c": 102.0},
            {"t": "2026-07-10T16:00:00Z", "c": 98.0},
        ]

        outcomes = _option_outcomes(
            alpaca,
            [
                {
                    "id": "signal-1",
                    "symbol": "AAPL260710C00100000",
                    "date": "2026-07-10",
                    "timestamp_iso": "2026-07-10T14:30:00Z",
                    "underlying": "AAPL",
                    "expiration_date": "2026-07-10",
                    "strike_price": 100,
                    "contract_type": "call",
                    "entry_price": 2.5,
                    "entry_iv": 0.3,
                    "entry_spot": 100,
                }
            ],
        )

        outcome = outcomes["signal-1"]
        self.assertEqual(outcome["high"], 4.2)
        self.assertEqual(outcome["low"], 1.4)
        self.assertTrue(outcome["went_up"])
        self.assertTrue(outcome["high_greeks"]["estimated"])
        self.assertTrue(outcome["low_greeks"]["estimated"])

    def test_option_outcomes_uses_saved_path_when_option_bars_fail(self):
        alpaca = MagicMock()
        alpaca.get_option_bars.side_effect = AlpacaApiError("subscription does not permit option bars")
        alpaca.get_stock_bars.return_value = []

        outcomes = _option_outcomes(
            alpaca,
            [
                {
                    "id": "signal-2",
                    "symbol": "QQQ260710C00715000",
                    "date": "2026-07-10",
                    "timestamp_iso": "2026-07-10T14:30:00Z",
                    "underlying": "QQQ",
                    "expiration_date": "2026-07-10",
                    "strike_price": 715,
                    "contract_type": "call",
                    "entry_price": 10.0,
                    "entry_iv": 0.3,
                    "fallback_delta": 0.4,
                    "fallback_gamma": 0.02,
                    "fallback_path": [10.0, 12.5, 9.5],
                }
            ],
        )

        outcome = outcomes["signal-2"]
        self.assertEqual(outcome["high"], 12.5)
        self.assertEqual(outcome["low"], 9.5)
        self.assertEqual(outcome["source"], "saved intraday path fallback")
        self.assertEqual(outcome["high_greeks"]["delta"], 0.4)

    def test_option_outcomes_returns_row_error_without_bars_or_fallback(self):
        alpaca = MagicMock()
        alpaca.get_option_bars.side_effect = AlpacaApiError("option bars unavailable")
        alpaca.get_stock_bars.return_value = []

        outcomes = _option_outcomes(
            alpaca,
            [
                {
                    "id": "signal-3",
                    "symbol": "QQQ260710C00715000",
                    "date": "2026-07-10",
                    "timestamp_iso": "2026-07-10T14:30:00Z",
                    "underlying": "QQQ",
                }
            ],
        )

        self.assertEqual(outcomes["signal-3"]["error"], "option bars unavailable")

    def test_historical_option_prices_uses_latest_bar_close(self):
        alpaca = MagicMock()
        alpaca.get_option_bars.return_value = {
            "QQQ260717C00720000": [
                {"t": "2026-07-13T14:30:00Z", "c": 2.1},
                {"t": "2026-07-13T15:00:00Z", "c": 2.85},
            ]
        }

        prices = _historical_option_prices(
            alpaca,
            ["QQQ260717C00720000"],
            "2026-07-13",
            "11:00:00",
        )

        self.assertEqual(prices["QQQ260717C00720000"]["mid"], 2.85)
        self.assertEqual(prices["QQQ260717C00720000"]["source"], "historical option bar")
        alpaca.get_option_bars.assert_called_once()

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
