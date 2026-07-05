import json
import unittest
from unittest.mock import MagicMock, patch

from trading_bot import gex_client
from trading_bot.config import Settings
from trading_bot.gex_client import (
    GexApiError,
    GexChain,
    GexClient,
    GexMajorLevels,
    GexMaxChange,
    StateGreekProfile,
    Tickers,
)


class TickersTests(unittest.TestCase):
    def test_from_json_normalizes_symbols(self):
        tickers = Tickers.from_json(
            {
                "stocks": ["aapl", " MSFT "],
                "indexes": ["SPX"],
                "futures": ["ES_SPX"],
            }
        )

        self.assertEqual(tickers.stocks, ("AAPL", "MSFT"))
        self.assertEqual(tickers.indexes, ("SPX",))
        self.assertEqual(tickers.futures, ("ES_SPX",))

    def test_from_json_rejects_bad_field(self):
        with self.assertRaisesRegex(GexApiError, "stocks"):
            Tickers.from_json({"stocks": None, "indexes": [], "futures": []})


class GexChainTests(unittest.TestCase):
    def test_from_json_reads_classic_chain(self):
        chain = GexChain.from_json(_gex_chain_payload())

        self.assertEqual(chain.timestamp, 1753283590)
        self.assertEqual(chain.ticker, "SPX")
        self.assertEqual(chain.min_dte, 0)
        self.assertEqual(chain.sec_min_dte, 1)
        self.assertEqual(chain.spot, 6326.5)
        self.assertEqual(chain.zero_gamma, 6323.8)
        self.assertEqual(chain.major_pos_vol, 6340.0)
        self.assertEqual(chain.major_neg_oi, 6300.0)
        self.assertEqual(chain.strikes[0].strike, 6110.0)
        self.assertEqual(chain.strikes[0].gex_by_volume, -0.17)
        self.assertEqual(chain.strikes[0].priors, (-0.17, -0.17, -0.21, -0.21, -0.24))
        self.assertEqual(chain.max_priors[0], (6325.0, -1418.293))

    def test_from_json_rejects_bad_strike_row(self):
        payload = _gex_chain_payload()
        payload["strikes"] = [[6110, -0.17]]

        with self.assertRaisesRegex(GexApiError, "strike row"):
            GexChain.from_json(payload)


class GexMajorLevelsTests(unittest.TestCase):
    def test_from_json_reads_major_levels(self):
        major_levels = GexMajorLevels.from_json(_gex_major_levels_payload())

        self.assertEqual(major_levels.timestamp, 1753283591)
        self.assertEqual(major_levels.ticker, "SPX")
        self.assertEqual(major_levels.spot, 6326.45)
        self.assertEqual(major_levels.mpos_vol, 6339.92)
        self.assertEqual(major_levels.mpos_oi, 6400.0)
        self.assertEqual(major_levels.mneg_vol, 6300.0)
        self.assertEqual(major_levels.mneg_oi, 6200.0)
        self.assertEqual(major_levels.zero_gamma, 6323.39)
        self.assertEqual(major_levels.net_gex_vol, 41199.07077)
        self.assertEqual(major_levels.net_gex_oi, 57505.37699)

    def test_from_json_rejects_bad_major_level(self):
        payload = _gex_major_levels_payload()
        payload["zero_gamma"] = None

        with self.assertRaisesRegex(GexApiError, "zero_gamma"):
            GexMajorLevels.from_json(payload)


class GexMaxChangeTests(unittest.TestCase):
    def test_from_json_reads_max_change(self):
        max_change = GexMaxChange.from_json(_gex_max_change_payload())

        self.assertEqual(max_change.timestamp, 1753283592)
        self.assertEqual(max_change.ticker, "SPX")
        self.assertEqual(max_change.current.strike, 6325.0)
        self.assertEqual(max_change.current.value, -1567.937)
        self.assertEqual(max_change.one.strike, 6340.0)
        self.assertEqual(max_change.five.value, -2542.092)
        self.assertEqual(max_change.ten.strike, 6315.0)
        self.assertEqual(max_change.fifteen.value, 4320.937)
        self.assertEqual(max_change.thirty.value, 8553.528)

    def test_from_json_rejects_bad_max_change_pair(self):
        payload = _gex_max_change_payload()
        payload["current"] = [6325]

        with self.assertRaisesRegex(GexApiError, "current"):
            GexMaxChange.from_json(payload)


class StateGreekProfileTests(unittest.TestCase):
    def test_from_json_reads_state_greek_profile(self):
        profile = StateGreekProfile.from_json(_state_greek_profile_payload())

        self.assertEqual(profile.timestamp, 1753283592)
        self.assertEqual(profile.ticker, "SPX")
        self.assertEqual(profile.spot, 6326.27)
        self.assertEqual(profile.min_dte, 0)
        self.assertEqual(profile.sec_min_dte, 1)
        self.assertEqual(profile.major_positive, 6345.0)
        self.assertEqual(profile.major_negative, 6280.08)
        self.assertEqual(profile.major_long_gamma, 6329.46)
        self.assertEqual(profile.major_short_gamma, 6335.55)
        self.assertEqual(profile.mini_contracts[1].strike, 6310.0)
        self.assertEqual(profile.mini_contracts[1].call_ivol, 0.126)
        self.assertEqual(profile.mini_contracts[1].put_ivol, 0.137)
        self.assertEqual(profile.mini_contracts[1].greek_value, 52.36)
        self.assertEqual(profile.mini_contracts[1].priors, (51.41, 57.72, 30.76))
        self.assertEqual(profile.mini_contracts[1].extra, (None, None))

    def test_from_json_rejects_bad_mini_contract_row(self):
        payload = _state_greek_profile_payload()
        payload["mini_contracts"] = [[6310, 0.126]]

        with self.assertRaisesRegex(GexApiError, "mini contract row"):
            StateGreekProfile.from_json(payload)


class GexClientTests(unittest.TestCase):
    def test_get_tickers_sends_required_headers(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)
        response = _mock_response(
            {
                "stocks": ["AAPL"],
                "indexes": ["SPX"],
                "futures": ["ES_SPX"],
            }
        )

        with patch("trading_bot.gex_client.urlopen", return_value=response) as urlopen_mock:
            tickers = client.get_tickers()

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/tickers")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(tickers.stocks, ("AAPL",))

    def test_get_tickers_rejects_non_object_response(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test")
        client = GexClient(settings)

        with patch("trading_bot.gex_client.urlopen", return_value=_mock_response([])):
            with self.assertRaisesRegex(GexApiError, "JSON object"):
                client.get_tickers()

    def test_get_gex_chain_sends_expected_path(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)

        with patch("trading_bot.gex_client.urlopen", return_value=_mock_response(_gex_chain_payload())) as urlopen_mock:
            chain = client.get_gex_chain("spx", "zero")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/SPX/classic/zero")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(chain.ticker, "SPX")

    def test_get_gex_chain_rejects_bad_period(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test")
        client = GexClient(settings)

        with self.assertRaisesRegex(ValueError, "aggregation_period"):
            client.get_gex_chain("SPX", "bad")

    def test_get_state_gex_profile_sends_expected_path(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)

        with patch("trading_bot.gex_client.urlopen", return_value=_mock_response(_state_gex_profile_payload())) as urlopen_mock:
            profile = client.get_state_gex_profile("spx", "zero")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/SPX/state/zero")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(profile.ticker, "SPX")
        self.assertEqual(profile.sum_gex_vol, -597.68386)
        self.assertEqual(profile.strikes[0].gex_by_volume, -0.09)

    def test_get_gex_major_levels_sends_expected_path(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)

        with patch(
            "trading_bot.gex_client.urlopen",
            return_value=_mock_response(_gex_major_levels_payload()),
        ) as urlopen_mock:
            major_levels = client.get_gex_major_levels("spx", "full")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/SPX/classic/full/majors")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(major_levels.ticker, "SPX")

    def test_get_state_gex_major_levels_sends_expected_path(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)

        with patch(
            "trading_bot.gex_client.urlopen",
            return_value=_mock_response(_state_gex_major_levels_payload()),
        ) as urlopen_mock:
            major_levels = client.get_state_gex_major_levels("spx", "full")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/SPX/state/full/majors")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(major_levels.ticker, "SPX")
        self.assertEqual(major_levels.mpos_vol, 6345.0)
        self.assertEqual(major_levels.net_gex_vol, -200.55548)

    def test_get_gex_max_change_sends_expected_path(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)

        with patch(
            "trading_bot.gex_client.urlopen",
            return_value=_mock_response(_gex_max_change_payload()),
        ) as urlopen_mock:
            max_change = client.get_gex_max_change("spx", "full")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/SPX/classic/full/maxchange")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(max_change.ticker, "SPX")

    def test_get_state_gex_max_change_sends_expected_path(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)

        with patch(
            "trading_bot.gex_client.urlopen",
            return_value=_mock_response(_state_gex_max_change_payload()),
        ) as urlopen_mock:
            max_change = client.get_state_gex_max_change("spx", "full")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/SPX/state/full/maxchange")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(max_change.ticker, "SPX")
        self.assertEqual(max_change.current.strike, 6340.0)
        self.assertEqual(max_change.thirty.value, -337.716)

    def test_get_state_greek_profile_sends_expected_path(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test", user_agent="test/1.0")
        client = GexClient(settings)

        with patch(
            "trading_bot.gex_client.urlopen",
            return_value=_mock_response(_state_greek_profile_payload()),
        ) as urlopen_mock:
            profile = client.get_state_greek_profile("spx", "delta_zero")

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example.test/SPX/state/delta_zero")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "test/1.0")
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertEqual(profile.ticker, "SPX")

    def test_get_state_greek_profile_rejects_bad_greek(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test")
        client = GexClient(settings)

        with self.assertRaisesRegex(ValueError, "greek"):
            client.get_state_greek_profile("SPX", "delta")

    def test_historical_chain_refreshes_expired_signed_url(self):
        settings = Settings(api_key="secret", base_url="https://api.example.test")
        client = GexClient(settings)
        history_key = "SPX:classic:zero:2026-07-01"
        gex_client._HISTORICAL_ROWS_CACHE.clear()
        gex_client._HISTORICAL_ROW_CACHE.clear()
        gex_client._HISTORICAL_URL_CACHE.clear()
        gex_client._HISTORICAL_URL_CACHE[history_key] = "https://history.example.test/stale.json"

        with (
            patch("trading_bot.gex_client._read_disk_history_cache", return_value=None),
            patch("trading_bot.gex_client._read_disk_history_row", return_value=None),
            patch("trading_bot.gex_client._write_disk_history_row"),
            patch.object(client, "_get_json", return_value={"url": "https://history.example.test/fresh.json"}) as get_json,
            patch.object(
                client,
                "_get_signed_history_row",
                side_effect=[
                    GexApiError(
                        "GEX historical file request failed with HTTP 403: "
                        "AuthenticationFailed signed expiry time must be after signed start time"
                    ),
                    _gex_chain_payload(),
                ],
            ) as get_signed_history_row,
        ):
            chain = client._get_historical_chain("SPX", "classic", "zero", "2026-07-01", 1753283590)

        self.assertEqual(chain.ticker, "SPX")
        self.assertEqual(get_signed_history_row.call_args_list[0].args[0], "https://history.example.test/stale.json")
        self.assertEqual(get_signed_history_row.call_args_list[1].args[0], "https://history.example.test/fresh.json")
        self.assertEqual(gex_client._HISTORICAL_URL_CACHE[history_key], "https://history.example.test/fresh.json")
        get_json.assert_called_once_with("/hist/SPX/classic/zero/2026-07-01?noredirect")


def _mock_response(payload):
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps(payload).encode("utf-8")
    return response


def _gex_chain_payload():
    return {
        "timestamp": 1753283590,
        "ticker": "SPX",
        "min_dte": 0,
        "sec_min_dte": 1,
        "spot": 6326.5,
        "zero_gamma": 6323.8,
        "major_pos_vol": 6340,
        "major_pos_oi": 6330,
        "major_neg_vol": 6315,
        "major_neg_oi": 6300,
        "strikes": [
            [
                6110,
                -0.17,
                -10.65,
                [
                    -0.17,
                    -0.17,
                    -0.21,
                    -0.21,
                    -0.24,
                ],
            ],
            [
                6115,
                -0.07,
                -4.77,
                [
                    -0.07,
                    -0.07,
                    -0.07,
                    -0.07,
                    -0.01,
                ],
            ],
        ],
        "sum_gex_vol": 36316.42772,
        "sum_gex_oi": 15976.06365,
        "delta_risk_reversal": -1.486,
        "max_priors": [
            [
                6325,
                -1418.293,
            ],
            [
                6340,
                -1677.922,
            ],
        ],
    }


def _state_gex_profile_payload():
    payload = _gex_chain_payload()
    payload.update(
        {
            "timestamp": 1753283591,
            "spot": 6326.45,
            "zero_gamma": 0,
            "major_pos_vol": 6345,
            "major_pos_oi": 0,
            "major_neg_vol": 6280.08,
            "major_neg_oi": 0,
            "strikes": [
                [
                    6110,
                    -0.09,
                    0,
                    [
                        -0.09,
                        -0.09,
                        -0.17,
                        -0.17,
                        -0.22,
                    ],
                ],
                [
                    6115,
                    -0.01,
                    0,
                    [
                        -0.01,
                        -0.01,
                        -0.01,
                        -0.01,
                        0,
                    ],
                ],
            ],
            "sum_gex_vol": -597.68386,
            "sum_gex_oi": 0,
            "delta_risk_reversal": 0,
            "max_priors": [
                [
                    6340,
                    -29.431,
                ],
                [
                    6335,
                    97.079,
                ],
            ],
        }
    )
    return payload


def _gex_major_levels_payload():
    return {
        "timestamp": 1753283591,
        "ticker": "SPX",
        "spot": 6326.45,
        "mpos_vol": 6339.92,
        "mpos_oi": 6400,
        "mneg_vol": 6300,
        "mneg_oi": 6200,
        "zero_gamma": 6323.39,
        "net_gex_vol": 41199.07077,
        "net_gex_oi": 57505.37699,
    }


def _state_gex_major_levels_payload():
    return {
        "timestamp": 1753283592,
        "ticker": "SPX",
        "spot": 6326.27,
        "mpos_vol": 6345,
        "mpos_oi": 0,
        "mneg_vol": 6300,
        "mneg_oi": 0,
        "zero_gamma": 0,
        "net_gex_vol": -200.55548,
        "net_gex_oi": 0,
    }


def _gex_max_change_payload():
    return {
        "timestamp": 1753283592,
        "ticker": "SPX",
        "current": [
            6325,
            -1567.937,
        ],
        "one": [
            6340,
            -1997.391,
        ],
        "five": [
            6340,
            -2542.092,
        ],
        "ten": [
            6315,
            -2920.413,
        ],
        "fifteen": [
            6330,
            4320.937,
        ],
        "thirty": [
            6340,
            8553.528,
        ],
    }


def _state_gex_max_change_payload():
    return {
        "timestamp": 1753283592,
        "ticker": "SPX",
        "current": [
            6340,
            -32.156,
        ],
        "one": [
            6335,
            85.319,
        ],
        "five": [
            6330,
            -236.029,
        ],
        "ten": [
            6325,
            409.361,
        ],
        "fifteen": [
            6340,
            -795.71,
        ],
        "thirty": [
            6340,
            -337.716,
        ],
    }


def _state_greek_profile_payload():
    return {
        "timestamp": 1753283592,
        "ticker": "SPX",
        "spot": 6326.27,
        "min_dte": 0,
        "sec_min_dte": 1,
        "major_positive": 6345,
        "major_negative": 6280.08,
        "major_long_gamma": 6329.46,
        "major_short_gamma": 6335.55,
        "mini_contracts": [
            [
                6510,
                0.426,
                0,
                0,
                [
                    0,
                    0,
                    0,
                ],
                None,
                None,
            ],
            [
                6310,
                0.126,
                0.137,
                52.36,
                [
                    51.41,
                    57.72,
                    30.76,
                ],
                None,
                None,
            ],
        ],
    }


if __name__ == "__main__":
    unittest.main()
