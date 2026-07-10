import unittest

from trading_bot.options_analysis import OptionCandidate, OptionRecommendation
from trading_bot.options_replay import replay_option_recommendation


class OptionReplayTests(unittest.TestCase):
    def test_replay_ranks_candidates_from_historical_bars(self):
        replay = replay_option_recommendation(
            recommendation=_recommendation(),
            alpaca_client=_FakeAlpacaClient(),
            replay_date="2026-07-02",
            replay_time="10:00:25",
        )

        self.assertEqual(replay.date, "2026-07-02")
        self.assertEqual(replay.selected_time, "10:00:25")
        self.assertEqual(replay.candidates[0].symbol, "AAPL260710C00310000")
        self.assertGreater(replay.candidates[0].day_change_pct, 0)
        self.assertEqual(replay.candidates[0].price_path, (2.0, 2.4))


class _FakeAlpacaClient:
    def get_option_bars(self, symbols, **_kwargs):
        return {
            symbol: [
                {"t": "2026-07-02T13:30:00Z", "o": 2.0, "h": 2.1, "l": 1.9, "c": 2.0, "v": 10},
                {"t": "2026-07-02T14:00:00Z", "o": 2.1, "h": 2.5, "l": 2.0, "c": 2.4, "v": 200},
            ]
            for symbol in symbols
        }


def _recommendation():
    candidate = OptionCandidate(
        symbol="AAPL260710C00310000",
        underlying_symbol="AAPL",
        contract_type="call",
        expiration_date="2026-07-10",
        strike_price=310.0,
        bid=3.8,
        ask=3.94,
        mid=3.87,
        spread=0.14,
        spread_pct=0.036,
        open_interest=4992,
        delta=None,
        gamma=None,
        implied_volatility=None,
        score=95.0,
        reasons=(),
    )
    return OptionRecommendation(
        ticker="AAPL",
        underlying_symbol="AAPL",
        period="zero",
        gex_timestamp=1782919290,
        gex_spot=308.44,
        bias="neutral-bullish",
        contract_type="call",
        target_level=308.44,
        trade_permission="no trade",
        recommendation="Watch AAPL call.",
        candidates=(candidate,),
        warnings=(),
    )


if __name__ == "__main__":
    unittest.main()
