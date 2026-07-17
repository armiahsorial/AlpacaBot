import unittest

from trading_bot.analysis import GexAnalysis
from trading_bot.options_analysis import recommend_option_contracts


class OptionRecommendationTests(unittest.TestCase):
    def test_uses_native_spx_option_contracts(self):
        client = _FakeAlpacaClient()

        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(
                ticker="SPX",
                bias="bullish",
                score=4,
                permission="possible trade after confirmation",
            ),
            alpaca_client=client,
        )

        self.assertEqual(client.requested_underlying, "SPX")
        self.assertEqual(recommendation.underlying_symbol, "SPX")
        self.assertFalse(any("using SPY as proxy" in warning for warning in recommendation.warnings))

    def test_databento_uses_native_ndx_contracts_with_gex_spot(self):
        client = _FakeAlpacaClient()
        client.provider_name = "databento"

        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(
                ticker="NDX",
                bias="bullish",
                score=4,
                permission="possible trade after confirmation",
            ),
            alpaca_client=client,
        )

        self.assertEqual(client.requested_underlying, "NDX")
        self.assertEqual(recommendation.underlying_symbol, "NDX")
        self.assertIn("sourced from GEX", recommendation.candidates[0].reasons[0])

    def test_recommends_call_for_bullish_gex(self):
        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(bias="bullish", score=4, permission="possible trade after confirmation"),
            alpaca_client=_FakeAlpacaClient(),
        )

        self.assertEqual(recommendation.contract_type, "call")
        self.assertEqual(recommendation.candidates[0].symbol, "AAPL260110C00200000")
        self.assertIn("Watch", recommendation.recommendation)

    def test_estimates_missing_greeks_from_mid_price(self):
        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(bias="bullish", score=4, permission="possible trade after confirmation"),
            alpaca_client=_FakeAlpacaClient(include_greeks=False),
        )

        candidate = recommendation.candidates[0]
        self.assertTrue(candidate.greeks_estimated)
        self.assertIsNotNone(candidate.delta)
        self.assertIsNotNone(candidate.gamma)
        self.assertIsNotNone(candidate.implied_volatility)

    def test_filters_candidates_above_maximum_contract_cost(self):
        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(bias="bullish", score=4, permission="possible trade after confirmation"),
            alpaca_client=_FakeAlpacaClient(),
            max_contract_cost=200,
        )

        self.assertEqual(recommendation.candidates, ())
        self.assertIn("contract-price limit", recommendation.warnings[-1])

    def test_returns_no_contract_for_neutral_gex(self):
        recommendation = recommend_option_contracts(
            gex_analysis=_analysis(bias="neutral", score=0, permission="no trade"),
            alpaca_client=_FakeAlpacaClient(),
        )

        self.assertIsNone(recommendation.contract_type)
        self.assertEqual(recommendation.candidates, ())
        self.assertIn("neutral", recommendation.recommendation)


class _FakeAlpacaClient:
    provider_name = "alpaca"

    def __init__(self, *, include_greeks: bool = True):
        self._include_greeks = include_greeks
        self.requested_underlying = None

    def get_option_contracts(self, underlying, **_kwargs):
        self.requested_underlying = underlying
        return [
            {
                "symbol": "AAPL260110C00200000",
                "underlying_symbol": "AAPL",
                "type": "call",
                "status": "active",
                "tradable": True,
                "expiration_date": "2026-07-17",
                "strike_price": "200",
                "open_interest": "1500",
            },
            {
                "symbol": "AAPL260110P00190000",
                "underlying_symbol": "AAPL",
                "type": "put",
                "status": "active",
                "tradable": True,
                "expiration_date": "2026-07-17",
                "strike_price": "190",
                "open_interest": "1500",
            },
        ]

    def get_option_snapshots(self, symbols):
        snapshots = {}
        for symbol in symbols:
            snapshot = {
                "latestQuote": {
                    "bp": 2.4,
                    "ap": 2.6,
                },
            }
            if self._include_greeks:
                snapshot["greeks"] = {"delta": 0.44, "gamma": 0.03}
                snapshot["impliedVolatility"] = 0.28
            snapshots[symbol] = snapshot
        return snapshots

    def get_option_bars(self, symbols, **_kwargs):
        return {symbol: [] for symbol in symbols}


def _analysis(*, bias: str, score: int, permission: str, ticker: str = "AAPL") -> GexAnalysis:
    return GexAnalysis(
        ticker=ticker,
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
