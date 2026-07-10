import unittest

from trading_bot.analysis import analyze_gex
from trading_bot.gex_client import GexChange, GexMajorLevels, GexMaxChange
from trading_bot.technicals import StockTechnicals


class AnalyzeGexTests(unittest.TestCase):
    def test_analyze_gex_returns_bullish_read_when_inputs_align(self):
        analysis = analyze_gex(
            period="zero",
            classic_major_levels=_major_levels(
                spot=6326.0,
                zero_gamma=6323.0,
                net_gex_vol=1000.0,
            ),
            state_major_levels=_major_levels(
                spot=6326.0,
                zero_gamma=0.0,
                net_gex_vol=500.0,
                mpos_vol=6345.0,
                mneg_vol=6300.0,
            ),
            classic_max_change=_max_change(thirty_value=100.0),
            state_max_change=_max_change(thirty_value=50.0),
        )

        self.assertEqual(analysis.bias, "bullish")
        self.assertEqual(analysis.confidence, "high")
        self.assertEqual(analysis.score, 5)
        self.assertEqual(analysis.trade_permission, "possible trade after confirmation")
        self.assertEqual(analysis.setup, "bullish hold above zero gamma")
        self.assertEqual(analysis.target_zone, "6340 to 6345.")
        self.assertEqual(analysis.invalidation, "Loss of zero gamma near 6323 or classic negative near 6300.")
        self.assertEqual(analysis.distance_to_zero_gamma, 3.0)
        self.assertEqual(analysis.upside_room, 14.0)
        self.assertEqual(analysis.downside_room, 26.0)
        self.assertEqual(analysis.no_trade_reasons, ())
        self.assertEqual(analysis.classic_major_positive, 6340.0)
        self.assertEqual(analysis.state_call_gamma_node, 6345.0)
        self.assertIn("Spot is above classic zero gamma", analysis.reasons[0])
        self.assertIn("+1 spot above zero gamma", analysis.score_breakdown)

    def test_analyze_gex_returns_neutral_when_inputs_conflict(self):
        analysis = analyze_gex(
            period="zero",
            classic_major_levels=_major_levels(
                spot=6320.0,
                zero_gamma=6323.0,
                net_gex_vol=1000.0,
            ),
            state_major_levels=_major_levels(
                spot=6320.0,
                zero_gamma=0.0,
                net_gex_vol=-500.0,
            ),
            classic_max_change=_max_change(thirty_value=100.0),
            state_max_change=_max_change(thirty_value=-50.0),
        )

        self.assertEqual(analysis.bias, "neutral-bearish")
        self.assertEqual(analysis.confidence, "low")
        self.assertEqual(analysis.trade_permission, "no trade")
        self.assertEqual(analysis.invalidation, "Reclaim of zero gamma near 6323 or classic positive near 6340.")
        self.assertIn("Signal alignment is weak.", analysis.no_trade_reasons)
        self.assertEqual(analysis.state_net_imbalance, -500.0)

    def test_analyze_gex_formats_inverted_bearish_levels_cleanly(self):
        analysis = analyze_gex(
            period="zero",
            classic_major_levels=_major_levels(
                spot=30264.6,
                zero_gamma=30274.8,
                net_gex_vol=-9711.02,
                mpos_vol=30300.0,
                mneg_vol=30250.0,
            ),
            state_major_levels=_major_levels(
                spot=30264.6,
                zero_gamma=0.0,
                net_gex_vol=-1935.37,
                mpos_vol=30040.0,
                mneg_vol=30240.0,
            ),
            classic_max_change=_max_change(strike=30250.0, thirty_value=-14182.01),
            state_max_change=_max_change(strike=30240.0, thirty_value=-838.95),
        )

        self.assertEqual(analysis.bias, "bearish")
        self.assertEqual(analysis.invalidation, "Reclaim of zero gamma near 30274.8 or classic positive near 30300.")
        self.assertEqual(analysis.target_zone, "30240 to 30250.")
        self.assertEqual(analysis.avoid_zone, "Avoid chasing bearish trades into 30240 to 30250.")

    def test_analyze_gex_includes_technical_context_in_score(self):
        analysis = analyze_gex(
            period="zero",
            classic_major_levels=_major_levels(spot=6326.0, zero_gamma=6323.0, net_gex_vol=1000.0),
            state_major_levels=_major_levels(spot=6326.0, zero_gamma=0.0, net_gex_vol=500.0),
            classic_max_change=_max_change(thirty_value=100.0),
            state_max_change=_max_change(thirty_value=50.0),
            technicals=StockTechnicals(
                symbol="SPY",
                as_of="2026-07-01T10:00:00-04:00",
                last_price=6326.0,
                vwap=6320.0,
                sma_50=6200.0,
                sma_200=6000.0,
                fibonacci_levels={"50%": 6000.0},
                fibonacci_near_sma_200={
                    "label": "50%",
                    "level": 6000.0,
                    "reference": 6000.0,
                    "distance": 0.0,
                    "distance_pct": 0.0,
                },
                intraday_volume=100000,
                score_adjustment=3,
                reasons=("Price is above VWAP.",),
                warnings=(),
            ),
        )

        self.assertEqual(analysis.score, 8)
        self.assertEqual(analysis.technicals.symbol, "SPY")
        self.assertIn("+3 VWAP/50-day/200-day technical context", analysis.score_breakdown)


def _major_levels(
    *,
    spot: float = 6326.0,
    zero_gamma: float = 6323.0,
    net_gex_vol: float = 1000.0,
    mpos_vol: float = 6340.0,
    mneg_vol: float = 6300.0,
) -> GexMajorLevels:
    return GexMajorLevels(
        timestamp=1753283591,
        ticker="SPX",
        spot=spot,
        mpos_vol=mpos_vol,
        mpos_oi=6400.0,
        mneg_vol=mneg_vol,
        mneg_oi=6200.0,
        zero_gamma=zero_gamma,
        net_gex_vol=net_gex_vol,
        net_gex_oi=500.0,
    )


def _max_change(*, thirty_value: float, strike: float = 6340.0) -> GexMaxChange:
    return GexMaxChange(
        timestamp=1753283592,
        ticker="SPX",
        current=GexChange(strike=6325.0, value=10.0),
        one=GexChange(strike=6325.0, value=10.0),
        five=GexChange(strike=6325.0, value=10.0),
        ten=GexChange(strike=6325.0, value=10.0),
        fifteen=GexChange(strike=6325.0, value=10.0),
        thirty=GexChange(strike=strike, value=thirty_value),
    )


if __name__ == "__main__":
    unittest.main()
