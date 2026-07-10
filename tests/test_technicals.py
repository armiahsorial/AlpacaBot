import unittest

from trading_bot.technicals import calculate_stock_technicals


class StockTechnicalsTests(unittest.TestCase):
    def test_calculates_vwap_moving_averages_and_fib_alignment(self):
        daily_bars = [
            {"h": 100 + index, "l": 100, "c": 100 + index}
            for index in range(200)
        ]
        minute_bars = [
            {"h": 300, "l": 296, "c": 298, "v": 100, "vw": 298},
            {"h": 302, "l": 298, "c": 300, "v": 300, "vw": 300},
        ]

        technicals = calculate_stock_technicals(
            symbol="AAPL",
            as_of="2026-07-01T10:00:00-04:00",
            minute_bars=minute_bars,
            daily_bars=daily_bars,
        )

        self.assertEqual(technicals.symbol, "AAPL")
        self.assertAlmostEqual(technicals.vwap, 299.5)
        self.assertAlmostEqual(technicals.sma_50, 274.5)
        self.assertAlmostEqual(technicals.sma_200, 199.5)
        self.assertIn("50%", technicals.fibonacci_levels)
        self.assertEqual(technicals.fibonacci_near_sma_200["label"], "50%")
        self.assertLess(technicals.fibonacci_near_sma_200["distance_pct"], 0.01)


if __name__ == "__main__":
    unittest.main()
