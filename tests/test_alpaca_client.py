import json
import unittest
from unittest.mock import patch

from trading_bot.alpaca_client import AlpacaApiError, AlpacaClient, PaperOrderRequest
from trading_bot.config import AlpacaSettings


class PaperOrderRequestTests(unittest.TestCase):
    def test_as_payload_validates_qty_or_notional(self):
        with self.assertRaisesRegex(ValueError, "qty or notional"):
            PaperOrderRequest(symbol="SPY", side="buy").as_payload()

    def test_as_payload_normalizes_order(self):
        payload = PaperOrderRequest(symbol=" spy ", side="BUY", qty=1.5, type="market").as_payload()

        self.assertEqual(payload["symbol"], "SPY")
        self.assertEqual(payload["side"], "buy")
        self.assertEqual(payload["qty"], 1.5)
        self.assertEqual(payload["type"], "market")
        self.assertEqual(payload["time_in_force"], "day")


class AlpacaClientTests(unittest.TestCase):
    def test_get_account_sends_alpaca_headers(self):
        client = AlpacaClient(_settings())

        with patch("trading_bot.alpaca_client.urlopen", return_value=_mock_response({"status": "ACTIVE"})) as mock:
            account = client.get_account()

        request = mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://paper.example.test/v2/account")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Apca-api-key-id"], "paper-key")
        self.assertEqual(request.headers["Apca-api-secret-key"], "paper-secret")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(account["status"], "ACTIVE")

    def test_submit_order_posts_json_to_paper_endpoint(self):
        client = AlpacaClient(_settings())
        response = _mock_response({"symbol": "SPY", "status": "accepted"})

        with patch("trading_bot.alpaca_client.urlopen", return_value=response) as mock:
            order = client.submit_order(PaperOrderRequest(symbol="SPY", side="buy", qty=1))

        request = mock.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://paper.example.test/v2/orders")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertEqual(body["symbol"], "SPY")
        self.assertEqual(body["side"], "buy")
        self.assertEqual(body["qty"], 1)
        self.assertEqual(order["status"], "accepted")

    def test_latest_bar_uses_data_endpoint(self):
        client = AlpacaClient(_settings())

        with patch("trading_bot.alpaca_client.urlopen", return_value=_mock_response({"bars": {"SPY": {}}})) as mock:
            client.get_latest_bar("spy", feed="iex")

        request = mock.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://data.example.test/v2/stocks/bars/latest?symbols=SPY&feed=iex",
        )

    def test_get_option_contracts_uses_paper_endpoint(self):
        client = AlpacaClient(_settings())
        payload = {"option_contracts": [{"symbol": "SPY260117C00450000"}]}

        with patch("trading_bot.alpaca_client.urlopen", return_value=_mock_response(payload)) as mock:
            contracts = client.get_option_contracts(
                "spy",
                expiration_date_gte="2026-01-01",
                expiration_date_lte="2026-01-15",
            )

        request = mock.call_args.args[0]
        self.assertIn("https://paper.example.test/v2/options/contracts?", request.full_url)
        self.assertIn("underlying_symbols=SPY", request.full_url)
        self.assertIn("expiration_date_gte=2026-01-01", request.full_url)
        self.assertEqual(contracts[0]["symbol"], "SPY260117C00450000")

    def test_get_option_snapshots_uses_data_endpoint(self):
        client = AlpacaClient(_settings())

        with patch("trading_bot.alpaca_client.urlopen", return_value=_mock_response({"snapshots": {"ABC": {}}})) as mock:
            snapshots = client.get_option_snapshots(["abc"])

        request = mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://data.example.test/v1beta1/options/snapshots?symbols=ABC")
        self.assertEqual(snapshots, {"ABC": {}})

    def test_get_option_bars_uses_data_endpoint(self):
        client = AlpacaClient(_settings())
        payload = {"bars": {"ABC": [{"c": 1.2}]}}

        with patch("trading_bot.alpaca_client.urlopen", return_value=_mock_response(payload)) as mock:
            bars = client.get_option_bars(["abc"], start="2026-01-02T14:30:00Z", end="2026-01-02T21:00:00Z")

        request = mock.call_args.args[0]
        self.assertIn("https://data.example.test/v1beta1/options/bars?", request.full_url)
        self.assertIn("symbols=ABC", request.full_url)
        self.assertIn("timeframe=1Min", request.full_url)
        self.assertEqual(bars["ABC"][0]["c"], 1.2)

    def test_get_account_rejects_non_object(self):
        client = AlpacaClient(_settings())

        with patch("trading_bot.alpaca_client.urlopen", return_value=_mock_response([])):
            with self.assertRaisesRegex(AlpacaApiError, "JSON object"):
                client.get_account()


def _settings():
    return AlpacaSettings(
        api_key_id="paper-key",
        api_secret_key="paper-secret",
        paper_base_url="https://paper.example.test",
        data_base_url="https://data.example.test",
        user_agent="test/1.0",
    )


class _mock_response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
