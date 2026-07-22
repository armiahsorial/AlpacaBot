import tempfile
import unittest
from pathlib import Path

from trading_bot.storage import TradingBotStorage


class TradingBotStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "history.sqlite3"
        self.storage = TradingBotStorage(self.database_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sync_imports_and_updates_records_idempotently(self):
        history = {
            "id": "permission-1",
            "replayDate": "2026-07-17",
            "timestamp": {"iso": "2026-07-17T15:30:00Z"},
            "ticker": "spx",
            "symbol": "SPXW260717C07500000",
            "entryPrice": 4.05,
        }
        ledger = {
            "id": "ledger:permission-1",
            "day": "2026-07-17",
            "timestamp": {"iso": "2026-07-17T15:30:00Z"},
            "ticker": "spx",
            "symbol": "SPXW260717C07500000",
            "status": "open",
            "currentPrice": 4.05,
        }

        self.storage.sync(
            trade_history=[history],
            paper_ledger=[ledger],
            tracked_tickers={"2026-07-17": ["SPX", "NDX"]},
        )
        updated_history = {**history, "outcome": {"high": 13.90}}
        updated_ledger = {**ledger, "status": "closed", "currentPrice": 6.45}
        self.storage.sync(
            trade_history=[updated_history],
            paper_ledger=[updated_ledger],
            tracked_tickers={"2026-07-17": ["SPX", "NDX"]},
        )

        snapshot = self.storage.snapshot()
        self.assertEqual(len(snapshot["trade_history"]), 1)
        self.assertEqual(snapshot["trade_history"][0]["outcome"]["high"], 13.90)
        self.assertEqual(len(snapshot["paper_ledger"]), 1)
        self.assertEqual(snapshot["paper_ledger"][0]["status"], "closed")
        self.assertEqual(snapshot["tracked_tickers"]["2026-07-17"], ["NDX", "SPX"])
        self.assertEqual(snapshot["database_path"], str(self.database_path.resolve()))

    def test_delete_day_preserves_other_dates(self):
        records = [
            {
                "id": f"permission-{day}",
                "replayDate": day,
                "ticker": "SPX",
                "symbol": "SPXW260717C07500000",
            }
            for day in ("2026-07-16", "2026-07-17")
        ]
        self.storage.sync(trade_history=records)

        deleted = self.storage.delete_day("trade_history", "2026-07-17")

        self.assertEqual(deleted, 1)
        self.assertEqual(
            [row["replayDate"] for row in self.storage.snapshot()["trade_history"]],
            ["2026-07-16"],
        )

    def test_history_for_day_returns_only_requested_records(self):
        self.storage.sync(
            trade_history=[
                {"id": "p-16", "replayDate": "2026-07-16", "ticker": "QQQ"},
                {"id": "p-17", "replayDate": "2026-07-17", "ticker": "SPX"},
            ],
            paper_ledger=[
                {"id": "l-17", "day": "2026-07-17", "ticker": "SPX", "status": "open"},
            ],
            tracked_tickers={"2026-07-17": ["SPX", "AMD"]},
        )

        result = self.storage.history_for_day("2026-07-17")

        self.assertEqual([row["id"] for row in result["trade_history"]], ["p-17"])
        self.assertEqual([row["id"] for row in result["paper_ledger"]], ["l-17"])
        self.assertEqual(result["tracked_tickers"], ["AMD", "SPX"])
        self.assertEqual(result["date"], "2026-07-17")

    def test_option_bar_cache_round_trips_by_provider_date_and_symbol(self):
        bars = {
            "AMD260717C00487500": [
                {"t": "2026-07-17T15:24:00Z", "h": 4.1, "c": 4.0},
                {"t": "2026-07-17T17:30:00Z", "h": 18.0, "c": 17.5},
            ]
        }
        self.assertEqual(self.storage.save_option_bars("databento", "2026-07-17", bars), 1)

        loaded = self.storage.option_bars(
            "databento",
            "2026-07-17",
            ["AMD260717C00487500", "AMD260717C00485000"],
        )

        self.assertEqual(loaded, bars)

    def test_complete_historical_cache_round_trips_without_replacing_history(self):
        stock_bars = [{"t": "2026-07-17T15:30:00Z", "c": 628.0}]
        gex_rows = {
            "classic": [{"timestamp": 1, "ticker": "SPX"}],
            "state": [{"timestamp": 1, "ticker": "SPX"}],
        }
        self.storage.sync(trade_history=[{
            "id": "permission-cache",
            "replayDate": "2026-07-17",
            "ticker": "SPX",
            "symbol": "SPXW260717C07500000",
        }])
        self.storage.save_stock_bars("databento", "2026-07-17", "SPY", "1Min", stock_bars)
        self.storage.save_gex_rows("2026-07-17", "SPX", "zero", gex_rows)
        self.storage.save_cache_status(
            "2026-07-17", "SPX", "zero", "databento",
            status="complete", option_contract_count=1, detail={"stock_symbol": "SPY"},
        )

        self.assertEqual(
            self.storage.stock_bars("databento", "2026-07-17", "SPY", "1Min"),
            stock_bars,
        )
        self.assertEqual(self.storage.gex_rows("2026-07-17", "SPX", "zero"), gex_rows)
        status = self.storage.cache_status("2026-07-17", period="zero", provider="databento")
        self.assertEqual(status[0]["status"], "complete")
        self.assertEqual(status[0]["option_contract_count"], 1)
        self.assertEqual(len(self.storage.snapshot()["trade_history"]), 1)

    def test_gex_rows_at_uses_timestamp_index_and_keeps_original_rows(self):
        def row(timestamp, spot):
            return {
                "timestamp": timestamp,
                "ticker": "SPX",
                "min_dte": 0,
                "sec_min_dte": 0,
                "spot": spot,
                "zero_gamma": 7500.0,
                "major_pos_vol": 7520.0,
                "major_pos_oi": 7525.0,
                "major_neg_vol": 7480.0,
                "major_neg_oi": 7475.0,
                "strikes": [[7500.0, 1.0, 2.0, []]],
                "sum_gex_vol": 10.0,
                "sum_gex_oi": 20.0,
                "delta_risk_reversal": 0.0,
                "max_priors": [[7500.0, 1.0]],
            }

        rows = {
            "classic": [row(100, 7501.0), row(200, 7502.0)],
            "state": [row(100, 7503.0), row(200, 7504.0)],
            "vanna": [{
                "timestamp": 100,
                "ticker": "SPX",
                "major_positive": 7520.0,
                "major_negative": 7480.0,
                "mini_contracts": [[7500.0, 0.2, 0.3, 12.0, []]],
            }],
            "charm": [{
                "timestamp": 100,
                "ticker": "SPX",
                "major_positive": 7520.0,
                "major_negative": 7480.0,
                "mini_contracts": [[7500.0, 0.2, 0.3, -5.0, []]],
            }],
        }
        self.storage.save_gex_rows("2026-07-20", "SPX", "zero", rows)

        selected = self.storage.gex_rows_at("2026-07-20", "SPX", "zero", 150)

        self.assertEqual(selected["classic"][0]["spot"], 7501.0)
        self.assertEqual(selected["state"][0]["spot"], 7503.0)
        self.assertEqual(selected["vanna"][0]["net_greek"], 12.0)
        self.assertEqual(selected["charm"][0]["net_greek"], -5.0)
        self.assertEqual(selected["classic"][0]["strikes"], [])
        stored = self.storage.gex_rows("2026-07-20", "SPX", "zero")
        self.assertEqual(stored["classic"], rows["classic"])
        self.assertEqual(stored["state"], rows["state"])
        self.assertEqual(stored["vanna"][0]["net_greek"], 12.0)
        self.assertEqual(stored["charm"][0]["net_greek"], -5.0)

    def test_delete_day_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            self.storage.delete_day("unknown", "2026-07-17")
        with self.assertRaises(ValueError):
            self.storage.delete_day("trade_history", "07/17/2026")


if __name__ == "__main__":
    unittest.main()
