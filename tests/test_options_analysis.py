import unittest

from trading_bot.analysis import GexAnalysis
from trading_bot.options_analysis import recommend_option_contracts


class OptionRecommendationTests(unittest.TestCase):
    def test_recommends_call_for_bullish_gex(self):
        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(bias="bullish", score=4, permission="possible trade after confirmation"),
            alpaca_client=_FakeAlpacaClient(),
        )

        self.assertEqual(recommendation.contract_type, "call")
        self.assertEqual(recommendation.candidates[0].symbol, "AAPL260110C00200000")
        self.assertIn("Watch", recommendation.recommendation)

    def test_returns_no_contract_for_neutral_gex(self):
        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(bias="neutral", score=0, permission="no trade"),
            alpaca_client=_FakeAlpacaClient(),
        )

        self.assertIsNone(recommendation.contract_type)
        self.assertEqual(recommendation.candidates, ())
        self.assertIn("neutral", recommendation.recommendation)


class _FakeAlpacaClient:
    def get_option_contracts(self, *_args, **_kwargs):
        return [
            {
                "symbol": "AAPL260110C00200000",
                "underlying_symbol": "AAPL",
                "type": "call",
                "status": "active",
                "tradable": True,
                "expiration_date": "2026-01-10",
                "strike_price": "200",
                "open_interest": "1500",
            },
            {
                "symbol": "AAPL260110P00190000",
                "underlying_symbol": "AAPL",
                "type": "put",
                "status": "active",
                "tradable": True,
                "expiration_date": "2026-01-10",
                "strike_price": "190",
                "open_interest": "1500",
            },
        ]

    def get_option_snapshots(self, symbols):
        return {
            symbol: {
                "latestQuote": {
                    "bp": 2.4,
                    "ap": 2.6,
                },
                "greeks": {"delta": 0.44, "gamma": 0.03},
                "impliedVolatility": 0.28,
            }
            for symbol in symbols
        }


def _analysis(*, bias: str, score: int, permission: str) -> GexAnalysis:
    return GexAnalysis(
        ticker="AAPL",
        period="zero",
        timestamp=1782919290,
        spot=195.0,
        zero_gamma=192.0,
        score=score,
        market_regime="positive gamma with supportive state flow",
        bias=bias,
        confidence="high",
        trade_permission=permission,
        setup="bullish hold above zero gamma",
        entry_trigger="-",
        invalidation="-",
        target_zone="-",
        avoid_zone="-",
        action="-",
        risk_note="-",
        classic_major_positive=200.0,
        classic_major_negative=190.0,
        state_call_gamma_node=201.0,
        state_put_gamma_node=189.0,
        classic_net_gex=100.0,
        state_net_imbalance=100.0,
        classic_thirty_min_change=(200.0, 50.0),
        state_thirty_min_change=(200.0, 50.0),
        distance_to_zero_gamma=3.0,
        upside_room=5.0,
        downside_room=5.0,
        reasons=(),
        score_breakdown=(),
        no_trade_reasons=(),
    )


if __name__ == "__main__":
    unittest.main()
