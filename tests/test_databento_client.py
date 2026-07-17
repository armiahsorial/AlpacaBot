import unittest
from unittest.mock import MagicMock

from trading_bot.databento_client import (
    DatabentoClient,
    OPTION_PARENT_ROOTS,
    _from_databento_option_symbol,
    _normalize_bar,
    _normalize_contract,
    _to_databento_option_symbol,
)
from trading_bot.config import DatabentoSettings


class DatabentoClientTests(unittest.TestCase):
    def test_index_option_roots_include_weekly_contract_families(self):
        self.assertEqual(OPTION_PARENT_ROOTS["SPX"], ("SPX", "SPXW"))
        self.assertEqual(OPTION_PARENT_ROOTS["NDX"], ("NDX", "NDXP"))

    def test_translates_occ_symbols_both_directions(self):
        compact = "AAPL260717C00310000"
        raw = _to_databento_option_symbol(compact)
        self.assertEqual(raw, "AAPL  260717C00310000")
        self.assertEqual(_from_databento_option_symbol(raw), compact)

    def test_normalizes_definition_to_existing_contract_shape(self):
        contract = _normalize_contract(
            {
                "raw_symbol": "SPXW  260717P07610000",
                "expiration": "2026-07-17T20:00:00+00:00",
                "strike_price": 7610.0,
            },
            "SPX",
        )
        self.assertIsNotNone(contract)
        self.assertEqual(contract["symbol"], "SPXW260717P07610000")
        self.assertEqual(contract["type"], "put")
        self.assertEqual(contract["expiration_date"], "2026-07-17")
        self.assertEqual(contract["strike_price"], 7610.0)

    def test_definition_past_its_exact_expiration_is_inactive(self):
        contract = _normalize_contract(
            {
                "raw_symbol": "SPX   200117C03300000",
                "expiration": "2020-01-17T14:30:00+00:00",
                "strike_price": 3300.0,
            },
            "SPX",
        )
        self.assertIsNotNone(contract)
        self.assertEqual(contract["status"], "inactive")

    def test_normalizes_nanosecond_bar_prices(self):
        bar = _normalize_bar(
            {
                "t": "2026-07-16T13:30:00Z",
                "open": 3_200_000_000,
                "high": 3_500_000_000,
                "low": 3_100_000_000,
                "close": 3_400_000_000,
                "volume": 42,
            }
        )
        self.assertEqual(bar["o"], 3.2)
        self.assertEqual(bar["h"], 3.5)
        self.assertEqual(bar["l"], 3.1)
        self.assertEqual(bar["c"], 3.4)
        self.assertEqual(bar["v"], 42)

    def test_stock_bars_use_configured_alpaca_provider(self):
        fallback = MagicMock()
        fallback.get_stock_bars.return_value = [{"t": "2026-07-16T13:30:00Z", "c": 620.0}]
        client = DatabentoClient(DatabentoSettings(api_key="key"), equities_fallback=fallback)
        client._bar_rows = MagicMock()

        bars = client.get_stock_bars(
            "SPY",
            start="2026-07-16T13:30:00Z",
            end="2026-07-16T14:00:00Z",
            timeframe="1Min",
        )

        self.assertEqual(bars[0]["c"], 620.0)
        client._bar_rows.assert_not_called()
        fallback.get_stock_bars.assert_called_once_with(
            "SPY",
            start="2026-07-16T13:30:00Z",
            end="2026-07-16T14:00:00Z",
            timeframe="1Min",
            feed="iex",
            limit=10000,
        )


if __name__ == "__main__":
    unittest.main()
