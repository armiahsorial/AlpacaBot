"""Command line interface for trading_bot."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from trading_bot.analysis import GexAnalysis, analyze_gex
from trading_bot.config import Settings
from trading_bot.gex_client import (
    AGGREGATION_PERIODS,
    GexApiError,
    GexChain,
    GexClient,
    GexMajorLevels,
    GexMaxChange,
    STATE_GREEKS,
    StateGreekProfile,
    Tickers,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "tickers":
            client = _gex_client()
            tickers = client.get_tickers()
            _print_tickers(tickers, group=args.group, as_json=args.as_json)
            return 0

        if args.command == "gex-chain":
            client = _gex_client()
            chain = client.get_gex_chain(args.ticker, args.period)
            _print_gex_chain(chain, as_json=args.as_json, limit=args.limit)
            return 0

        if args.command == "state-profile":
            client = _gex_client()
            profile = client.get_state_gex_profile(args.ticker, args.period)
            _print_state_gex_profile(profile, as_json=args.as_json, limit=args.limit)
            return 0

        if args.command == "gex-majors":
            client = _gex_client()
            major_levels = client.get_gex_major_levels(args.ticker, args.period)
            _print_gex_major_levels(major_levels, as_json=args.as_json)
            return 0

        if args.command == "state-majors":
            client = _gex_client()
            major_levels = client.get_state_gex_major_levels(args.ticker, args.period)
            _print_state_gex_major_levels(major_levels, as_json=args.as_json)
            return 0

        if args.command == "gex-maxchange":
            client = _gex_client()
            max_change = client.get_gex_max_change(args.ticker, args.period)
            _print_gex_max_change(max_change, as_json=args.as_json, title="classic GEX max change")
            return 0

        if args.command == "state-maxchange":
            client = _gex_client()
            max_change = client.get_state_gex_max_change(args.ticker, args.period)
            _print_gex_max_change(max_change, as_json=args.as_json, title="state GEX max imbalance change")
            return 0

        if args.command == "state-greeks":
            client = _gex_client()
            profile = client.get_state_greek_profile(args.ticker, args.greek)
            _print_state_greek_profile(profile, greek=args.greek, as_json=args.as_json, limit=args.limit)
            return 0

        if args.command == "analyze":
            client = _gex_client()
            classic_major_levels = client.get_gex_major_levels(args.ticker, args.period)
            state_major_levels = client.get_state_gex_major_levels(args.ticker, args.period)
            classic_max_change = client.get_gex_max_change(args.ticker, args.period)
            state_max_change = client.get_state_gex_max_change(args.ticker, args.period)
            analysis = analyze_gex(
                period=args.period,
                classic_major_levels=classic_major_levels,
                state_major_levels=state_major_levels,
                classic_max_change=classic_max_change,
                state_max_change=state_max_change,
            )
            _print_gex_analysis(analysis, as_json=args.as_json)
            return 0

        parser.print_help()
        return 2
    except (GexApiError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-bot")
    subparsers = parser.add_subparsers(dest="command")

    tickers_parser = subparsers.add_parser("tickers", help="List GEX-supported ticker symbols.")
    tickers_parser.add_argument(
        "--group",
        choices=("stocks", "indexes", "futures"),
        help="Limit output to one ticker group.",
    )
    tickers_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    gex_chain_parser = subparsers.add_parser("gex-chain", help="Fetch classic GEX chain data.")
    gex_chain_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    gex_chain_parser.add_argument(
        "--period",
        choices=AGGREGATION_PERIODS,
        default="zero",
        help="Aggregation period. Defaults to zero.",
    )
    gex_chain_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of strike rows to print in table mode. Defaults to 10.",
    )
    gex_chain_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    state_profile_parser = subparsers.add_parser("state-profile", help="Fetch state GEX imbalance profile.")
    state_profile_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    state_profile_parser.add_argument(
        "--period",
        choices=AGGREGATION_PERIODS,
        default="zero",
        help="Aggregation period. Defaults to zero.",
    )
    state_profile_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of strike rows to print in table mode. Defaults to 10.",
    )
    state_profile_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    gex_majors_parser = subparsers.add_parser("gex-majors", help="Fetch classic GEX major levels.")
    gex_majors_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    gex_majors_parser.add_argument(
        "--period",
        choices=AGGREGATION_PERIODS,
        default="zero",
        help="Aggregation period. Defaults to zero.",
    )
    gex_majors_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    state_majors_parser = subparsers.add_parser("state-majors", help="Fetch state GEX major imbalance levels.")
    state_majors_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    state_majors_parser.add_argument(
        "--period",
        choices=AGGREGATION_PERIODS,
        default="zero",
        help="Aggregation period. Defaults to zero.",
    )
    state_majors_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    gex_maxchange_parser = subparsers.add_parser("gex-maxchange", help="Fetch classic GEX max changes.")
    gex_maxchange_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    gex_maxchange_parser.add_argument(
        "--period",
        choices=AGGREGATION_PERIODS,
        default="zero",
        help="Aggregation period. Defaults to zero.",
    )
    gex_maxchange_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    state_maxchange_parser = subparsers.add_parser("state-maxchange", help="Fetch state GEX max imbalance changes.")
    state_maxchange_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    state_maxchange_parser.add_argument(
        "--period",
        choices=AGGREGATION_PERIODS,
        default="zero",
        help="Aggregation period. Defaults to zero.",
    )
    state_maxchange_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    state_greeks_parser = subparsers.add_parser("state-greeks", help="Fetch state orderflow Greek profile.")
    state_greeks_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    state_greeks_parser.add_argument(
        "greek",
        choices=STATE_GREEKS,
        help="State Greek profile to fetch.",
    )
    state_greeks_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of mini-contract rows to print in table mode. Defaults to 10.",
    )
    state_greeks_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a table.",
    )

    analyze_parser = subparsers.add_parser("analyze", help="Analyze GEX levels and state imbalance.")
    analyze_parser.add_argument("ticker", help="Ticker symbol, such as SPX.")
    analyze_parser.add_argument(
        "--period",
        choices=AGGREGATION_PERIODS,
        default="zero",
        help="Aggregation period. Defaults to zero.",
    )
    analyze_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON instead of a report.",
    )

    return parser


def _gex_client() -> GexClient:
    return GexClient(Settings.from_env())


def _print_tickers(tickers: Tickers, group: str | None, as_json: bool) -> None:
    data = tickers.as_dict()
    if group:
        data = {group: data[group]}

    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return

    for name, symbols in data.items():
        print(f"{name}:")
        print("  " + ", ".join(symbols))


def _print_gex_chain(chain: GexChain, as_json: bool, limit: int) -> None:
    if as_json:
        print(json.dumps(chain.as_dict(), indent=2, sort_keys=True))
        return

    limit = max(limit, 0)
    visible_strikes = chain.strikes[:limit]

    print(f"{chain.ticker} classic GEX chain")
    print(f"timestamp: {chain.timestamp}")
    print(f"spot: {chain.spot:g}")
    print(f"min_dte: {chain.min_dte}")
    print(f"sec_min_dte: {chain.sec_min_dte}")
    print(f"zero_gamma: {chain.zero_gamma:g}")
    print(f"sum_gex_vol: {chain.sum_gex_vol:g}")
    print(f"sum_gex_oi: {chain.sum_gex_oi:g}")
    print()
    print("major levels:")
    print(f"  major_pos_vol: {chain.major_pos_vol:g}")
    print(f"  major_pos_oi: {chain.major_pos_oi:g}")
    print(f"  major_neg_vol: {chain.major_neg_vol:g}")
    print(f"  major_neg_oi: {chain.major_neg_oi:g}")

    if not visible_strikes:
        return

    print()
    print(f"strikes first {len(visible_strikes)} of {len(chain.strikes)}:")
    print("  strike      gex_vol      gex_oi      priors")
    for strike in visible_strikes:
        priors = ", ".join(f"{value:g}" for value in strike.priors)
        print(
            f"  {strike.strike:>6g}"
            f"  {strike.gex_by_volume:>11g}"
            f"  {strike.gex_by_open_interest:>10g}"
            f"      [{priors}]"
        )


def _print_state_gex_profile(profile: GexChain, as_json: bool, limit: int) -> None:
    if as_json:
        print(json.dumps(profile.as_dict(), indent=2, sort_keys=True))
        return

    limit = max(limit, 0)
    visible_strikes = profile.strikes[:limit]

    print(f"{profile.ticker} state GEX imbalance profile")
    print(f"timestamp: {profile.timestamp}")
    print(f"spot: {profile.spot:g}")
    print(f"min_dte: {profile.min_dte}")
    print(f"sec_min_dte: {profile.sec_min_dte}")
    print(f"zero_gamma: {profile.zero_gamma:g}")
    print(f"net_gex_imbalance: {profile.sum_gex_vol:g}")
    print()
    print("imbalance levels:")
    print(f"  call_gamma_node: {profile.major_pos_vol:g}")
    print(f"  put_gamma_node: {profile.major_neg_vol:g}")

    if not visible_strikes:
        return

    print()
    print(f"strikes first {len(visible_strikes)} of {len(profile.strikes)}:")
    print("  strike    imbalance      priors")
    for strike in visible_strikes:
        priors = ", ".join(f"{value:g}" for value in strike.priors)
        print(f"  {strike.strike:>6g}  {strike.gex_by_volume:>11g}      [{priors}]")


def _print_gex_major_levels(major_levels: GexMajorLevels, as_json: bool) -> None:
    if as_json:
        print(json.dumps(major_levels.as_dict(), indent=2, sort_keys=True))
        return

    print(f"{major_levels.ticker} classic GEX major levels")
    print(f"timestamp: {major_levels.timestamp}")
    print(f"spot: {major_levels.spot:g}")
    print(f"zero_gamma: {major_levels.zero_gamma:g}")
    print(f"net_gex_vol: {major_levels.net_gex_vol:g}")
    print(f"net_gex_oi: {major_levels.net_gex_oi:g}")
    print()
    print("major levels:")
    print(f"  mpos_vol: {major_levels.mpos_vol:g}")
    print(f"  mpos_oi: {major_levels.mpos_oi:g}")
    print(f"  mneg_vol: {major_levels.mneg_vol:g}")
    print(f"  mneg_oi: {major_levels.mneg_oi:g}")


def _print_state_gex_major_levels(major_levels: GexMajorLevels, as_json: bool) -> None:
    if as_json:
        print(json.dumps(major_levels.as_dict(), indent=2, sort_keys=True))
        return

    print(f"{major_levels.ticker} state GEX major imbalance levels")
    print(f"timestamp: {major_levels.timestamp}")
    print(f"spot: {major_levels.spot:g}")
    print(f"net_gex_imbalance: {major_levels.net_gex_vol:g}")
    print()
    print("imbalance levels:")
    print(f"  call_gamma_node: {major_levels.mpos_vol:g}")
    print(f"  put_gamma_node: {major_levels.mneg_vol:g}")


def _print_gex_max_change(max_change: GexMaxChange, as_json: bool, title: str) -> None:
    if as_json:
        print(json.dumps(max_change.as_dict(), indent=2, sort_keys=True))
        return

    rows = [
        ("current", max_change.current),
        ("1 minute", max_change.one),
        ("5 minutes", max_change.five),
        ("10 minutes", max_change.ten),
        ("15 minutes", max_change.fifteen),
        ("30 minutes", max_change.thirty),
    ]

    print(f"{max_change.ticker} {title}")
    print(f"timestamp: {max_change.timestamp}")
    print()
    print("lookback       strike       gex_change")
    for label, change in rows:
        print(f"{label:<10}  {change.strike:>8g}  {change.value:>15g}")


def _print_state_greek_profile(profile: StateGreekProfile, greek: str, as_json: bool, limit: int) -> None:
    if as_json:
        print(json.dumps(profile.as_dict(), indent=2, sort_keys=True))
        return

    limit = max(limit, 0)
    visible_contracts = profile.mini_contracts[:limit]

    print(f"{profile.ticker} state {greek} profile")
    print(f"timestamp: {profile.timestamp}")
    print(f"spot: {profile.spot:g}")
    print(f"min_dte: {profile.min_dte}")
    print(f"sec_min_dte: {profile.sec_min_dte}")
    print()
    print("major levels:")
    print(f"  major_positive: {profile.major_positive:g}")
    print(f"  major_negative: {profile.major_negative:g}")
    print(f"  major_long_gamma: {profile.major_long_gamma:g}")
    print(f"  major_short_gamma: {profile.major_short_gamma:g}")

    if not visible_contracts:
        return

    print()
    print(f"mini contracts first {len(visible_contracts)} of {len(profile.mini_contracts)}:")
    print("  strike   call_ivol   put_ivol   greek_value   priors")
    for contract in visible_contracts:
        priors = ", ".join(f"{value:g}" for value in contract.priors)
        print(
            f"  {contract.strike:>6g}"
            f"  {contract.call_ivol:>10g}"
            f"  {contract.put_ivol:>9g}"
            f"  {contract.greek_value:>12g}"
            f"   [{priors}]"
        )


def _print_gex_analysis(analysis: GexAnalysis, as_json: bool) -> None:
    if as_json:
        print(json.dumps(analysis.as_dict(), indent=2, sort_keys=True))
        return

    print(f"{analysis.ticker} GEX analysis")
    print(f"period: {analysis.period}")
    print(f"spot: {analysis.spot:g}")
    print(f"zero_gamma: {analysis.zero_gamma:g}")
    print(f"market_regime: {analysis.market_regime}")
    print(f"bias: {analysis.bias}")
    print(f"confidence: {analysis.confidence}")
    print(f"score: {analysis.score}")
    print(f"trade_permission: {analysis.trade_permission}")
    print(f"setup: {analysis.setup}")
    print()
    print("key levels:")
    print(f"  classic_major_positive: {analysis.classic_major_positive:g}")
    print(f"  classic_major_negative: {analysis.classic_major_negative:g}")
    print(f"  state_call_gamma_node: {analysis.state_call_gamma_node:g}")
    print(f"  state_put_gamma_node: {analysis.state_put_gamma_node:g}")
    print()
    print("pressure:")
    print(f"  classic_net_gex: {analysis.classic_net_gex:g}")
    print(f"  state_net_imbalance: {analysis.state_net_imbalance:g}")
    print(
        "  classic_30m_change: "
        f"{analysis.classic_thirty_min_change[1]:g} at {analysis.classic_thirty_min_change[0]:g}"
    )
    print(
        "  state_30m_change: "
        f"{analysis.state_thirty_min_change[1]:g} at {analysis.state_thirty_min_change[0]:g}"
    )
    print()
    print("distance:")
    print(f"  distance_to_zero_gamma: {_format_optional_number(analysis.distance_to_zero_gamma)}")
    print(f"  upside_room: {_format_optional_number(analysis.upside_room)}")
    print(f"  downside_room: {_format_optional_number(analysis.downside_room)}")
    print()
    print("trade plan:")
    print(f"  entry_trigger: {analysis.entry_trigger}")
    print(f"  invalidation: {analysis.invalidation}")
    print(f"  target_zone: {analysis.target_zone}")
    print(f"  avoid_zone: {analysis.avoid_zone}")
    print()
    print("read:")
    for reason in analysis.reasons:
        print(f"  - {reason}")
    print()
    print("score breakdown:")
    for item in analysis.score_breakdown:
        print(f"  - {item}")
    if analysis.no_trade_reasons:
        print()
        print("no-trade reasons:")
        for item in analysis.no_trade_reasons:
            print(f"  - {item}")
    print()
    print(f"action: {analysis.action}")
    print(f"risk: {analysis.risk_note}")


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:g}"


if __name__ == "__main__":
    raise SystemExit(main())
