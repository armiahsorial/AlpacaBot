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

    def test_delete_day_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            self.storage.delete_day("unknown", "2026-07-17")
        with self.assertRaises(ValueError):
            self.storage.delete_day("trade_history", "07/17/2026")


if __name__ == "__main__":
    unittest.main()
