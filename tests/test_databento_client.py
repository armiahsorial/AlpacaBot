import unittest
from threading import Barrier, Lock, Thread
from time import sleep
from unittest.mock import MagicMock

from trading_bot.databento_client import (
    DatabentoClient,
    OPTION_PARENT_ROOTS,
    _from_databento_option_symbol,
    _normalize_bar,
    _normalize_contract,
    _to_databento_option_symbol,
    _weekly_option_alias,
)
from trading_bot.config import DatabentoSettings


class DatabentoClientTests(unittest.TestCase):
    def test_stream_setup_does_not_hold_snapshot_callback_lock(self):
        client = DatabentoClient(DatabentoSettings(api_key="key"))

        def simulate_stream_setup(symbols):
            def deliver_callback():
                with client._live_option_lock:
                    client._live_option_snapshots[symbols[0]] = {
                        "latestQuote": {"bp": 4.0, "ap": 4.2}
                    }

            callback_thread = Thread(target=deliver_callback)
            callback_thread.start()
            callback_thread.join(timeout=0.5)
            self.assertFalse(callback_thread.is_alive(), "stream callback was blocked by the request lock")

        client._ensure_live_option_stream = MagicMock(side_effect=simulate_stream_setup)

        snapshots = client.get_streaming_option_snapshots(["SPXW260721C07500000"])

        self.assertIn("SPXW260721C07500000", snapshots)

    def test_index_option_roots_include_weekly_contract_families(self):
        self.assertEqual(OPTION_PARENT_ROOTS["SPX"], ("SPX", "SPXW"))
        self.assertEqual(OPTION_PARENT_ROOTS["NDX"], ("NDX", "NDXP"))

    def test_translates_occ_symbols_both_directions(self):
        compact = "AAPL260717C00310000"
        raw = _to_databento_option_symbol(compact)
        self.assertEqual(raw, "AAPL  260717C00310000")
        self.assertEqual(_from_databento_option_symbol(raw), compact)

    def test_maps_legacy_index_contracts_to_weekly_roots(self):
        self.assertEqual(
            _weekly_option_alias("SPX260717P07320000"),
            "SPXW260717P07320000",
        )
        self.assertEqual(
            _weekly_option_alias("NDX260717C29140000"),
            "NDXP260717C29140000",
        )
        self.assertIsNone(_weekly_option_alias("QQQ260717P00707000"))

    def test_option_bars_fall_back_to_weekly_index_root(self):
        client = DatabentoClient(DatabentoSettings(api_key="key"))
        client._bar_rows = MagicMock(side_effect=[
            [],
            [{
                "symbol": "SPXW260717P07320000",
                "t": "2026-07-16T19:49:00Z",
                "open": 670_000_000,
                "high": 690_000_000,
                "low": 650_000_000,
                "close": 670_000_000,
                "volume": 173,
            }],
        ])

        bars = client.get_option_bars(
            ["SPX260717P07320000"],
            start="2026-07-16T19:48:10Z",
            end="2026-07-16T20:00:00Z",
        )

        self.assertEqual(bars["SPX260717P07320000"][0]["c"], 0.67)
        self.assertEqual(client._bar_rows.call_count, 2)
        alias_request = client._bar_rows.call_args_list[1].kwargs["symbols"]
        self.assertEqual(alias_request, ["SPXW  260717P07320000"])

    def test_option_bars_prefer_weekly_series_when_exact_series_is_stale(self):
        client = DatabentoClient(DatabentoSettings(api_key="key"))
        client._bar_rows = MagicMock(side_effect=[
            [{
                "symbol": "SPX260717P07320000",
                "t": "2026-07-16T18:25:00Z",
                "close": 400_000_000,
            }],
            [{
                "symbol": "SPXW260717P07320000",
                "t": "2026-07-16T19:59:00Z",
                "close": 250_000_000,
            }],
        ])

        bars = client.get_option_bars(
            ["SPX260717P07320000"],
            start="2026-07-16T13:30:00Z",
            end="2026-07-16T20:00:00Z",
        )

        self.assertEqual(bars["SPX260717P07320000"][0]["t"], "2026-07-16T19:59:00Z")
        self.assertEqual(bars["SPX260717P07320000"][0]["c"], 0.25)

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

    def test_historical_requests_do_not_force_unsupported_raw_to_raw_mapping(self):
        client = DatabentoClient(DatabentoSettings(api_key="key"))
        historical = MagicMock()
        historical.timeseries.get_range.return_value.to_df.return_value.reset_index.return_value.to_dict.return_value = []
        client._historical_client = historical

        client._historical_rows(
            dataset="OPRA.PILLAR",
            schema="ohlcv-1m",
            symbols=["AMD   260717C00487500"],
            stype_in="raw_symbol",
            start="2026-07-17T15:23:37Z",
            end="2026-07-17T20:00:00Z",
        )

        kwargs = historical.timeseries.get_range.call_args.kwargs
        self.assertEqual(kwargs["stype_in"], "raw_symbol")
        self.assertNotIn("stype_out", kwargs)

    def test_historical_frame_materialization_is_serialized(self):
        client = DatabentoClient(DatabentoSettings(api_key="key"))
        historical = MagicMock()
        client._historical_client = historical
        barrier = Barrier(3)
        state_lock = Lock()
        active = 0
        max_active = 0

        def get_range(**kwargs):
            del kwargs
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            sleep(0.02)
            with state_lock:
                active -= 1
            data = MagicMock()
            data.to_df.return_value.reset_index.return_value.to_dict.return_value = []
            return data

        historical.timeseries.get_range.side_effect = get_range

        def request_rows():
            barrier.wait()
            client._historical_rows(
                dataset="OPRA.PILLAR",
                schema="ohlcv-1m",
                symbols=["NDXP 260717C29140000"],
                stype_in="raw_symbol",
                start="2026-07-17T16:00:00Z",
                end="2026-07-17T17:00:00Z",
            )

        threads = [Thread(target=request_rows) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(max_active, 1)


if __name__ == "__main__":
    unittest.main()
