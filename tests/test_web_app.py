import json
import unittest
from io import BytesIO
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from trading_bot.alpaca_client import AlpacaApiError
from trading_bot.web_app import (
    STATIC_DIR,
    TradingBotWebHandler,
    _historical_option_prices,
    _option_price_from_snapshot,
    _option_outcomes,
    _stock_technicals,
)


class WebAppTests(unittest.TestCase):
    def test_option_snapshot_rejects_extremely_wide_quote_midpoint(self):
        price = _option_price_from_snapshot({
            "latestQuote": {"bp": 4.0, "ap": 146.0},
            "latestTrade": {"p": 4.25},
        })

        self.assertEqual(price["mid"], 4.25)
        self.assertEqual(price["bid"], 4.0)
        self.assertEqual(price["ask"], 146.0)

    def test_option_snapshot_returns_no_mark_for_wide_quote_without_trade(self):
        price = _option_price_from_snapshot({
            "latestQuote": {"bp": 4.0, "ap": 146.0},
        })

        self.assertIsNone(price["mid"])

    def test_frontend_replaces_corrupt_ledger_high_with_authoritative_bars(self):
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn('const authoritative = outcome.source === "market-data option bars"', javascript)
        self.assertIn("const current = reliableOptionMark(priceMap?.[trade.symbol])", javascript)
        self.assertIn("spreadRatio > 0.50", javascript)
        self.assertIn("const displayedHistoryOutcomes = new Map()", javascript)
        self.assertIn('replayOutcome?.source === "market-data option bars"', javascript)
        self.assertIn("function refreshHistoricalPaperLedgerOutcomes(ledger, replayPoint)", javascript)

    def test_frontend_defaults_to_spx_and_fifteen_second_refreshes(self):
        html = (STATIC_DIR / "index.html").read_text()
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn('value="SPX" data-ticker-checkbox checked', html)
        self.assertIn('value="NDX" data-ticker-checkbox checked', html)
        self.assertEqual(html.count('<option value="15" selected>15 sec</option>'), 2)
        self.assertIn('Math.max(15, Number(liveInterval.value || 15))', javascript)
        self.assertIn('return selected.length > 0 ? [...new Set(selected)] : ["NDX", "SPX"]', javascript)
        self.assertIn("function selectedReplayUsesLiveData()", javascript)
        self.assertIn("if (!day || day > currentHostDate() || isWeekendDate(day))", javascript)

    def test_frontend_uses_compact_local_time_replay_controls(self):
        html = (STATIC_DIR / "index.html").read_text()
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn("<h1>Trading Bot</h1>", html)
        self.assertIn('<option value="1000" selected>$1,000</option>', html)
        self.assertNotIn('id="live-update"', html)
        self.assertIn('id="tracking-overview-rows"', html)
        self.assertIn('const TRACKING_HISTORY_STORAGE_KEY = "tradingBot.trackedTickersByDate"', javascript)
        self.assertIn("function hostMarketWindow(dateValue)", javascript)
        self.assertIn("const REPLAY_FETCH_STEP_SECONDS = 60", javascript)
        self.assertIn("function scheduleReplayScrubRefresh()", javascript)
        self.assertIn("function historyItemVisibleAtReplayPoint(item, selectedDate, replayPoint = null)", javascript)
        self.assertIn('id="replay-clock" type="time" step="1"', html)
        self.assertIn("function parseClock(value)", javascript)
        self.assertIn("replayTime.value = String(Math.min(", javascript)

    def test_replay_updates_historical_rows_at_selected_speed(self):
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn("const REPLAY_CLOCK_TICK_MS = 100", javascript)
        self.assertIn("replayClockRemainder += replaySpeed * (REPLAY_CLOCK_TICK_MS / 1000)", javascript)
        self.assertIn("const nextValue = Math.min(previousValue + wholeSeconds", javascript)
        self.assertIn("replayTimer = setTimeout(runReplayClockTick, REPLAY_CLOCK_TICK_MS)", javascript)
        self.assertIn("if (crossedMinute) {", javascript)
        self.assertIn("renderTradeHistory();", javascript)
        self.assertIn("loadOptionReplay({ refreshHistory: false })", javascript)
        self.assertIn("renderOptionReplays(payloads, errors, { refreshHistory })", javascript)

    def test_same_day_slider_uses_replay_cutoff_instead_of_live_day_shortcut(self):
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn('replayTime.addEventListener("input", () => {\n  // Moving the replay clock', javascript)
        self.assertIn("&& liveTimer !== null", javascript)
        self.assertIn("const isReplayView = Boolean(selectedDate && !selectedReplayUsesLiveData())", javascript)
        self.assertIn("paperLedgerVisibleAtReplayPoint(trade, selectedDate, replayPoint)", javascript)
        self.assertNotIn("if (!selectedDate || selectedDate === currentHostDate())", javascript)
        self.assertIn("const REPLAY_MIN_FETCH_INTERVAL_MS = 15000", javascript)
        self.assertIn("function getReplayPoint()", javascript)

    def test_frontend_uses_sticky_watchlist_and_fast_replay_updates(self):
        html = (STATIC_DIR / "index.html").read_text()
        javascript = (STATIC_DIR / "app.js").read_text()
        stylesheet = (STATIC_DIR / "styles.css").read_text()

        self.assertIn('class="watchlist-sidebar"', html)
        self.assertIn('class="watchlist-main"', html)
        self.assertIn("position: sticky", stylesheet)
        self.assertIn(".history-high-label", stylesheet)
        self.assertIn("const replayOutcomeCache = new Map()", javascript)
        self.assertIn("Promise.allSettled([outcomeUpdate, updateTradeHistoryPrices(history)])", javascript)
        self.assertIn("}, 300);", javascript)

    def test_market_snapshot_and_report_are_inside_sticky_sidebar(self):
        html = (STATIC_DIR / "index.html").read_text()
        stylesheet = (STATIC_DIR / "styles.css").read_text()

        sidebar_start = html.index('class="watchlist-sidebar"')
        sidebar_end = html.index('class="watchlist-main"')
        insights = html.index('id="sidebar-insights"')
        tracking = html.index('id="tracking-overview-rows"')

        self.assertLess(sidebar_start, tracking)
        self.assertLess(tracking, insights)
        self.assertLess(insights, sidebar_end)
        self.assertEqual(html.count('id="trade-permission"'), 1)
        self.assertEqual(html.count('id="technical-vwap"'), 1)
        self.assertEqual(html.count('id="report-profitable"'), 1)
        self.assertIn(".sidebar-report .report-card-grid", stylesheet)
        self.assertIn("max-height: calc(100vh - 24px)", stylesheet)

    def test_paper_ledger_reuses_saved_price_paths_without_api_requests(self):
        javascript = (STATIC_DIR / "app.js").read_text()
        stylesheet = (STATIC_DIR / "styles.css").read_text()

        self.assertIn("pricePath: Array.isArray(item.pricePath) ? item.pricePath.slice(-120) : [entry]", javascript)
        self.assertIn("function paperLedgerPricePath(trade, current = null)", javascript)
        self.assertIn("optionSparklineMarkup({ price_path: ledgerPricePath })", javascript)
        self.assertIn("pricePath: appendPaperLedgerPrice(trade.pricePath, current)", javascript)
        self.assertIn(".ledger-price-chart .option-sparkline", stylesheet)

    def test_trade_history_rows_wrap_status_age_and_greeks_without_clipping(self):
        javascript = (STATIC_DIR / "app.js").read_text()
        stylesheet = (STATIC_DIR / "styles.css").read_text()

        self.assertIn('class="history-tags"', javascript)
        self.assertIn('class="history-stat history-recorded-stat"', javascript)
        self.assertIn('class="history-stat history-exit-stat"', javascript)
        self.assertIn("@media (max-width: 1750px) and (min-width: 761px)", stylesheet)
        self.assertIn(".trade-history-row .history-current-time", stylesheet)
        self.assertIn("min-height: 168px", stylesheet)

    def test_frontend_uses_confirmed_market_exit_rules_without_fixed_cash_simulation(self):
        html = (STATIC_DIR / "index.html").read_text()
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertNotIn("$10,000", html)
        self.assertNotIn('id="day-performance"', html)
        self.assertIn("const EXIT_CONFIRMATION_REFRESHES = 2", javascript)
        self.assertIn("Sell: trade permission disappeared", javascript)
        self.assertIn("Sell: spot fell below zero gamma", javascript)
        self.assertIn("Sell: underlying fell below VWAP", javascript)

    def test_frontend_caps_high_confidence_ledger_and_splits_trade_states(self):
        html = (STATIC_DIR / "index.html").read_text()
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn("const PAPER_LEDGER_DAILY_TRADE_LIMIT = 10", javascript)
        self.assertIn("const PAPER_LEDGER_MIN_SCORE = 100", javascript)
        self.assertIn("const PAPER_LEDGER_HIGHLIGHT_MS = 2 * 60 * 1000", javascript)
        self.assertIn('id="paper-ledger-open"', html)
        self.assertIn('id="paper-ledger-closed"', html)
        self.assertIn('id="force-close-paper-ledger"', html)
        self.assertIn('id="lower-confidence-log"', html)
        self.assertIn("function acknowledgePaperLedgerHighlight(id, state)", javascript)
        self.assertIn("function forceClosePaperTrades(tradeIds)", javascript)
        self.assertIn('exitReason: "Manual force close"', javascript)
        self.assertIn('data-ledger-force-close=', javascript)

    def test_frontend_streams_open_ledger_marks_without_rechecking_gex(self):
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn("ledgerPriceTimer = setInterval(refreshOpenPaperLedgerPrices, 1000)", javascript)
        self.assertIn("Entry only - awaiting live mark", javascript)
        self.assertIn("/api/options/stream-prices?", javascript)
        self.assertIn("{ evaluateExit: false }", javascript)

    def test_frontend_records_three_picks_without_duplicate_candidate_cards(self):
        html = (STATIC_DIR / "index.html").read_text()
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn("const MAX_RECORDED_PERMISSION_CANDIDATES = 3", javascript)
        self.assertEqual(javascript.count('limit: "3"'), 2)
        self.assertIn("renderTickerContractColumns(payloads, errors, \"live\")", javascript)
        self.assertIn("renderTickerContractColumns(payloads, errors, \"replay\")", javascript)
        self.assertIn('id="contract-list" class="hidden" aria-hidden="true"', html)
        renderer = javascript.split("function renderTickerContractColumns", 1)[1].split("function payloadHasTradePermission", 1)[0]
        self.assertNotIn("createTickerCandidateRow(", renderer)

    def test_frontend_preserves_scroll_during_auto_refresh(self):
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn("function captureViewportAnchor()", javascript)
        self.assertIn("function restoreViewportAnchor(anchor)", javascript)
        self.assertIn('fields.contractList.classList.add("is-refreshing")', javascript)
        self.assertNotIn('fields.contractList.textContent = "-"', javascript)
        self.assertIn("row.dataset.scrollKey", javascript)

    def test_frontend_compacts_trade_history_when_browser_storage_is_full(self):
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn("const COMPACT_TRADE_HISTORY_ITEMS = 600", javascript)
        self.assertIn("function compactTradeHistoryForStorage(history, limit)", javascript)
        self.assertIn("function compactDecisionSnapshot(snapshot)", javascript)
        self.assertNotIn('fields.tradeHistory.textContent = "Trade history could not be saved in this browser."', javascript)

    def test_frontend_hydrates_and_syncs_sqlite_storage(self):
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn('getJson("/api/storage/snapshot")', javascript)
        self.assertIn('postJson("/api/storage/sync"', javascript)
        self.assertIn('postJson("/api/storage/delete-day"', javascript)

    def test_historical_slider_and_reload_are_sqlite_only(self):
        html = (STATIC_DIR / "index.html").read_text()
        javascript = (STATIC_DIR / "app.js").read_text()

        self.assertIn('id="cache-day"', html)
        self.assertIn('id="replay-refresh" type="button">Reload SQLite', html)
        self.assertIn('local_only: "1"', javascript)
        self.assertNotIn('allowRemote: true', javascript)
        self.assertIn('local_only: Boolean(replayPoint)', javascript)
        self.assertIn('postJson("/api/cache/day"', javascript)
        self.assertIn("function mergePersistentRecords", javascript)
        self.assertIn("initializePersistentStorage();", javascript)

    def test_historical_trade_history_is_grouped_by_recorded_ticker(self):
        javascript = (STATIC_DIR / "app.js").read_text()
        stylesheet = (STATIC_DIR / "styles.css").read_text()

        self.assertIn("(isReplayView || matchesTickerFilter(item, selectedTickers))", javascript)
        self.assertIn("function renderHistoricalTickerGroups", javascript)
        self.assertIn("function historicalTickerSummaryMarkup", javascript)
        self.assertIn("function createTradeHistoryRow", javascript)
        self.assertIn('group.className = "history-ticker-group"', javascript)
        self.assertIn(".history-ticker-group > summary", stylesheet)
        self.assertIn('getJson(`/api/storage/history?date=${encodeURIComponent(day)}`)', javascript)
        self.assertIn("function historicalTradeHistoryForDate", javascript)
        self.assertIn("function historicalPaperLedgerForDate", javascript)
        self.assertIn('class="history-high-time"', javascript)
        self.assertIn("function formatOutcomeTimestamp", javascript)
        self.assertIn("historyOutcomeRequestVersions", javascript)
        self.assertGreaterEqual(javascript.count("if (!item) {\n        continue;"), 2)
        self.assertIn("A live snapshot here would overwrite that", javascript)
        self.assertIn("if (selectedDate && !selectedReplayUsesLiveData())", javascript)
        self.assertIn("const mergedOutcomes = replayPoint ? outcomes", javascript)
        self.assertIn("as_of_iso: replayPoint?.iso || null", javascript)
        self.assertIn("const outcomeBatchSize = replayPoint ? 1000 : 100", javascript)
        self.assertIn('class="history-current-time"', javascript)
        self.assertIn('<i>Last traded</i>', javascript)
        self.assertIn('const staleLabel = outcome.current_is_stale ? "stale · " : "";', javascript)
        self.assertIn("function postJsonWithRetry", javascript)
        self.assertIn("Historical replay unavailable after retry", javascript)

    def test_option_outcome_endpoint_supports_large_historical_ticker_groups(self):
        source = (STATIC_DIR.parent / "web_app.py").read_text()

        self.assertIn("if len(entries) > 1000:", source)
        self.assertIn("At most 1,000 option entries can be evaluated at once.", source)

    def test_handle_analyze_returns_analysis_json(self):
        handler = _handler()
        classic_major_levels = MagicMock()
        state_major_levels = MagicMock()
        classic_max_change = MagicMock()
        state_max_change = MagicMock()
        analysis = MagicMock()
        analysis.as_dict.return_value = {"ticker": "SPX", "bias": "neutral-bullish"}

        client = MagicMock()
        client.get_gex_major_levels.return_value = classic_major_levels
        client.get_state_gex_major_levels.return_value = state_major_levels
        client.get_gex_max_change.return_value = classic_max_change
        client.get_state_gex_max_change.return_value = state_max_change
        greek_flow = MagicMock()
        client.get_state_greek_flow.return_value = greek_flow

        with patch("trading_bot.web_app.Settings.from_env", return_value=MagicMock()):
            with patch("trading_bot.web_app.GexClient", return_value=client):
                with patch("trading_bot.web_app.analyze_gex", return_value=analysis) as analyze_mock:
                    handler._handle_analyze("ticker=spx&period=zero")

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(
            json.loads(handler.body.decode("utf-8")),
            {
                "ticker": "SPX",
                "bias": "neutral-bullish",
            },
        )
        client.get_gex_major_levels.assert_called_once_with("SPX", "zero")
        client.get_state_gex_major_levels.assert_called_once_with("SPX", "zero")
        client.get_gex_max_change.assert_called_once_with("SPX", "zero")
        client.get_state_gex_max_change.assert_called_once_with("SPX", "zero")
        analyze_mock.assert_called_once_with(
            period="zero",
            classic_major_levels=classic_major_levels,
            state_major_levels=state_major_levels,
            classic_max_change=classic_max_change,
            state_max_change=state_max_change,
            greek_flow=greek_flow,
        )

    def test_handle_analyze_rejects_bad_period(self):
        handler = _handler()

        handler._handle_analyze("ticker=spx&period=bad")

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("period", json.loads(handler.body.decode("utf-8"))["error"])

    def test_handle_alpaca_account_returns_account_json(self):
        handler = _handler()
        client = MagicMock()
        client.get_account.return_value = {"status": "ACTIVE", "cash": "100000"}

        with patch("trading_bot.web_app.AlpacaSettings.from_env", return_value=MagicMock()):
            with patch("trading_bot.web_app.AlpacaClient", return_value=client):
                handler._handle_alpaca_account()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(json.loads(handler.body.decode("utf-8"))["status"], "ACTIVE")
        client.get_account.assert_called_once_with()

    def test_handle_submit_alpaca_order_posts_order(self):
        body = json.dumps(
            {
                "symbol": "spy",
                "side": "buy",
                "qty": 1,
                "type": "market",
                "time_in_force": "day",
            }
        ).encode("utf-8")
        handler = _handler(body)
        client = MagicMock()
        client.submit_order.return_value = {"symbol": "SPY", "status": "accepted"}

        with patch("trading_bot.web_app.AlpacaSettings.from_env", return_value=MagicMock()):
            with patch("trading_bot.web_app.AlpacaClient", return_value=client):
                handler._handle_submit_alpaca_order()

        self.assertEqual(handler.status, HTTPStatus.CREATED)
        self.assertEqual(json.loads(handler.body.decode("utf-8"))["status"], "accepted")
        order = client.submit_order.call_args.args[0]
        self.assertEqual(order.symbol, "spy")
        self.assertEqual(order.side, "buy")
        self.assertEqual(order.qty, 1.0)

    def test_handle_option_recommendation_returns_json(self):
        handler = _handler()
        analysis = MagicMock()
        analysis.as_dict.return_value = {"ticker": "AAPL", "bias": "bullish"}
        recommendation = MagicMock()
        recommendation.as_dict.return_value = {"ticker": "AAPL", "candidates": []}

        with patch("trading_bot.web_app._analyze_ticker", return_value=analysis) as analyze_mock:
            with patch("trading_bot.web_app._market_data_client", return_value=MagicMock()) as market_data_mock:
                with patch("trading_bot.web_app.recommend_option_contracts", return_value=recommendation) as recommend_mock:
                    handler._handle_option_recommendation(
                        "ticker=aapl&period=zero&limit=3&max_contract_cost=500"
                    )

        self.assertEqual(handler.status, HTTPStatus.OK)
        payload = json.loads(handler.body.decode("utf-8"))
        self.assertEqual(payload["ticker"], "AAPL")
        self.assertEqual(payload["analysis"]["bias"], "bullish")
        analyze_mock.assert_called_once_with("AAPL", "zero")
        market_data_mock.assert_called_once_with()
        self.assertEqual(recommend_mock.call_args.kwargs["max_candidates"], 3)
        self.assertEqual(recommend_mock.call_args.kwargs["max_contract_cost"], 500)

    def test_handle_option_prices_returns_current_mids(self):
        handler = _handler()
        alpaca = MagicMock()
        alpaca.get_option_snapshots.return_value = {
            "AAPL260710C00310000": {
                "latestQuote": {"bp": 2.4, "ap": 2.6},
                "latestTrade": {"p": 2.55},
            }
        }

        with patch("trading_bot.web_app._market_data_client", return_value=alpaca):
            handler._handle_option_prices("symbols=AAPL260710C00310000")

        self.assertEqual(handler.status, HTTPStatus.OK)
        payload = json.loads(handler.body.decode("utf-8"))
        self.assertEqual(payload["prices"]["AAPL260710C00310000"]["mid"], 2.5)
        alpaca.get_option_snapshots.assert_called_once_with(["AAPL260710C00310000"])

    def test_handle_option_stream_prices_uses_persistent_stream_method(self):
        handler = _handler()
        market_data = MagicMock()
        market_data.get_streaming_option_snapshots.return_value = {
            "SPXW260721C07500000": {
                "latestQuote": {"bp": 4.0, "ap": 4.2},
            }
        }

        with patch("trading_bot.web_app._market_data_client", return_value=market_data):
            handler._handle_option_stream_prices("symbols=SPXW260721C07500000")

        self.assertEqual(handler.status, HTTPStatus.OK)
        payload = json.loads(handler.body.decode("utf-8"))
        self.assertTrue(payload["streaming"])
        self.assertEqual(payload["prices"]["SPXW260721C07500000"]["mid"], 4.1)

    def test_handle_option_replay_returns_json(self):
        handler = _handler()
        cached_payload = {
            "date": "2026-07-02",
            "candidates": [],
            "analysis": {"ticker": "AAPL", "bias": "bearish"},
        }

        with patch("trading_bot.web_app._cached_replay_payload", return_value=cached_payload) as cached_mock:
            handler._handle_option_replay("ticker=aapl&period=zero&date=2026-07-02&time=10:45:30")

        self.assertEqual(handler.status, HTTPStatus.OK)
        payload = json.loads(handler.body.decode("utf-8"))
        self.assertEqual(payload["date"], "2026-07-02")
        self.assertEqual(payload["analysis"]["bias"], "bearish")
        cached_mock.assert_called_once_with(
            storage=unittest.mock.ANY,
            ticker="AAPL",
            period="zero",
            replay_date="2026-07-02",
            replay_time="10:45:30",
            limit=5,
            max_contract_cost=None,
        )

    def test_stock_technicals_uses_iex_feed_for_alpaca_bars(self):
        alpaca = MagicMock()
        alpaca.get_stock_bars.return_value = []

        with patch("trading_bot.web_app._market_data_client", return_value=alpaca):
            _stock_technicals("AAPL", replay_date="2026-07-02", replay_time="10:45:30")

        self.assertEqual(alpaca.get_stock_bars.call_count, 2)
        for call in alpaca.get_stock_bars.call_args_list:
            self.assertEqual(call.kwargs["feed"], "iex")

    def test_option_outcomes_returns_high_low_and_estimated_greeks(self):
        alpaca = MagicMock()
        alpaca.provider_name = "databento"
        cached_bars = {
            "AAPL260710C00100000": [
                {"t": "2026-07-10T14:30:00Z", "h": 2.6, "l": 2.1, "c": 2.4},
                {"t": "2026-07-10T15:00:00Z", "h": 4.2, "l": 3.8, "c": 4.0},
                {"t": "2026-07-10T16:00:00Z", "h": 1.9, "l": 1.4, "c": 1.6},
            ]
        }
        cached_stock_bars = [
            {"t": "2026-07-10T14:30:00Z", "c": 100.0},
            {"t": "2026-07-10T15:00:00Z", "c": 102.0},
            {"t": "2026-07-10T16:00:00Z", "c": 98.0},
        ]

        cache = MagicMock()
        cache.option_bars.return_value = cached_bars
        cache.stock_bars.return_value = cached_stock_bars
        outcomes = _option_outcomes(
            alpaca,
            [
                {
                    "id": "signal-1",
                    "symbol": "AAPL260710C00100000",
                    "date": "2026-07-10",
                    "timestamp_iso": "2026-07-10T14:30:00Z",
                    "underlying": "AAPL",
                    "expiration_date": "2026-07-10",
                    "strike_price": 100,
                    "contract_type": "call",
                    "entry_price": 2.5,
                    "entry_iv": 0.3,
                    "entry_spot": 100,
                }
            ], option_bar_cache=cache,
        )

        outcome = outcomes["signal-1"]
        self.assertEqual(outcome["high"], 4.2)
        self.assertEqual(outcome["low"], 1.4)
        self.assertEqual(outcome["current"], 1.6)
        self.assertTrue(outcome["went_up"])
        self.assertTrue(outcome["high_greeks"]["estimated"])
        self.assertTrue(outcome["low_greeks"]["estimated"])

    def test_option_outcomes_local_only_never_calls_market_provider(self):
        market = MagicMock()
        market.provider_name = "databento"
        cache = MagicMock()
        cache.option_bars.return_value = {
            "AAPL260710C00100000": [
                {"t": "2026-07-10T14:30:00Z", "h": 2.6, "l": 2.1, "c": 2.4},
            ]
        }
        cache.stock_bars.return_value = []

        outcomes = _option_outcomes(
            market,
            [{
                "id": "local-only",
                "symbol": "AAPL260710C00100000",
                "date": "2026-07-10",
                "timestamp_iso": "2026-07-10T14:30:00Z",
                "underlying": "AAPL",
                "entry_price": 2.4,
            }],
            option_bar_cache=cache,
            allow_remote=False,
        )

        self.assertEqual(outcomes["local-only"]["current"], 2.4)
        market.get_option_bars.assert_not_called()
        market.get_stock_bars.assert_not_called()

    def test_completed_day_outcomes_never_call_provider_even_when_remote_is_allowed(self):
        market = MagicMock()
        market.provider_name = "databento"
        cache = MagicMock()
        cache.option_bars.return_value = {}
        cache.stock_bars.return_value = None

        outcomes = _option_outcomes(
            market,
            [{
                "id": "missing-cache-row",
                "symbol": "AAPL260710C00100000",
                "date": "2026-07-10",
                "timestamp_iso": "2026-07-10T14:30:00Z",
                "underlying": "AAPL",
                "entry_price": 2.4,
            }],
            option_bar_cache=cache,
            allow_remote=True,
        )

        self.assertIn("not cached in SQLite", outcomes["missing-cache-row"]["error"])
        market.get_option_bars.assert_not_called()
        market.get_stock_bars.assert_not_called()

    def test_historical_option_prices_never_call_provider(self):
        market = MagicMock()
        market.provider_name = "databento"
        cache = MagicMock()
        cache.option_bars.return_value = {}

        prices = _historical_option_prices(
            market,
            ["AAPL260710C00100000"],
            "2026-07-10",
            "12:00:00",
            option_bar_cache=cache,
        )

        self.assertIsNone(prices["AAPL260710C00100000"]["mid"])
        self.assertEqual(prices["AAPL260710C00100000"]["source"], "not cached in SQLite")
        market.get_option_bars.assert_not_called()

    def test_option_outcomes_uses_cached_gex_spot_for_index_greeks(self):
        market = MagicMock()
        market.provider_name = "databento"
        cache = MagicMock()
        cache.option_bars.return_value = {
            "SPXW260717P07450000": [
                {"t": "2026-07-17T14:30:00Z", "h": 8.0, "l": 7.5, "c": 7.8},
                {"t": "2026-07-17T15:00:00Z", "h": 12.0, "l": 10.0, "c": 11.5},
            ]
        }
        cache.stock_bars.return_value = [
            {"t": "2026-07-17T14:30:00Z", "c": 744.0},
            {"t": "2026-07-17T15:00:00Z", "c": 745.0},
        ]
        cache.gex_spot_rows.return_value = [
            {"timestamp": 1784298600, "spot": 7440.0},
            {"timestamp": 1784300400, "spot": 7450.0},
        ]

        with patch("trading_bot.web_app._solve_implied_volatility", return_value=0.25):
            with patch("trading_bot.web_app._black_scholes_delta", return_value=-0.4) as delta_mock:
                with patch("trading_bot.web_app._black_scholes_gamma", return_value=0.01):
                    outcomes = _option_outcomes(
                        market,
                        [{
                            "id": "spx-index-spot",
                            "symbol": "SPXW260717P07450000",
                            "date": "2026-07-17",
                            "timestamp_iso": "2026-07-17T14:30:00Z",
                            "underlying": "SPX",
                            "expiration_date": "2026-07-17",
                            "strike_price": 7450,
                            "contract_type": "put",
                            "entry_price": 7.8,
                            "entry_spot": 7440,
                        }],
                        option_bar_cache=cache,
                        allow_remote=False,
                    )

        self.assertEqual(outcomes["spx-index-spot"]["high_greeks"]["delta"], -0.4)
        self.assertIn(7450.0, {call.args[1] for call in delta_mock.call_args_list})
        self.assertNotIn(745.0, {call.args[1] for call in delta_mock.call_args_list})
        cache.gex_spot_rows.assert_called_once_with("2026-07-17", "SPX")

    def test_option_outcomes_uses_saved_path_when_option_bars_fail(self):
        alpaca = MagicMock()
        alpaca.get_option_bars.side_effect = AlpacaApiError("subscription does not permit option bars")
        alpaca.get_stock_bars.return_value = []

        outcomes = _option_outcomes(
            alpaca,
            [
                {
                    "id": "signal-2",
                    "symbol": "QQQ260710C00715000",
                    "date": "2026-07-10",
                    "timestamp_iso": "2026-07-10T14:30:00Z",
                    "underlying": "QQQ",
                    "expiration_date": "2026-07-10",
                    "strike_price": 715,
                    "contract_type": "call",
                    "entry_price": 10.0,
                    "entry_iv": 0.3,
                    "fallback_delta": 0.4,
                    "fallback_gamma": 0.02,
                    "fallback_path": [10.0, 12.5, 9.5],
                }
            ],
        )

        outcome = outcomes["signal-2"]
        self.assertEqual(outcome["high"], 12.5)
        self.assertEqual(outcome["low"], 9.5)
        self.assertEqual(outcome["current"], 9.5)
        self.assertEqual(outcome["source"], "saved intraday path fallback")
        self.assertEqual(outcome["high_greeks"]["delta"], 0.4)

    def test_option_outcomes_stops_at_selected_replay_time(self):
        alpaca = MagicMock()
        alpaca.provider_name = "databento"
        cache = MagicMock()
        cache.option_bars.return_value = {
            "AAPL260710C00100000": [
                {"t": "2026-07-10T14:30:00Z", "h": 2.6, "l": 2.1, "c": 2.4},
                {"t": "2026-07-10T15:00:00Z", "h": 4.2, "l": 3.8, "c": 4.0},
                {"t": "2026-07-10T16:00:00Z", "h": 8.0, "l": 7.5, "c": 7.8},
            ]
        }
        cache.stock_bars.return_value = []

        outcomes = _option_outcomes(
            alpaca,
            [{
                "id": "signal-as-of",
                "symbol": "AAPL260710C00100000",
                "date": "2026-07-10",
                "timestamp_iso": "2026-07-10T14:30:00Z",
                "as_of_time": "11:00:00",
                "entry_price": 2.4,
            }], option_bar_cache=cache,
        )

        self.assertEqual(outcomes["signal-as-of"]["high"], 4.2)
        self.assertEqual(outcomes["signal-as-of"]["current"], 4.0)

    def test_option_outcomes_uses_exact_replay_instant_for_every_symbol(self):
        alpaca = MagicMock()
        alpaca.provider_name = "databento"
        cache = MagicMock()
        cache.option_bars.return_value = {
            "NDXP260717C29140000": [
                {"t": "2026-07-17T16:21:00Z", "h": 2.50, "l": 2.10, "c": 2.32},
                {"t": "2026-07-17T16:52:00Z", "h": 4.99, "l": 4.20, "c": 4.50},
                {"t": "2026-07-17T17:10:00Z", "h": 6.00, "l": 5.20, "c": 5.80},
            ],
            "SPXW260717C07500000": [
                {"t": "2026-07-17T16:31:00Z", "h": 3.20, "l": 2.80, "c": 3.00},
                {"t": "2026-07-17T16:52:00Z", "h": 5.25, "l": 4.70, "c": 5.00},
            ],
        }
        cache.stock_bars.return_value = []

        entries = [
            {
                "id": "ndx-signal",
                "symbol": "NDXP260717C29140000",
                "date": "2026-07-17",
                "timestamp_iso": "2026-07-17T16:00:00Z",
                "as_of_time": "09:31:00",
                "as_of_iso": "2026-07-17T16:52:06Z",
                "entry_price": 3.18,
            },
            {
                "id": "spx-signal",
                "symbol": "SPXW260717C07500000",
                "date": "2026-07-17",
                "timestamp_iso": "2026-07-17T16:00:00Z",
                "as_of_iso": "2026-07-17T16:52:06Z",
                "entry_price": 3.00,
            },
        ]

        outcomes = _option_outcomes(alpaca, entries, option_bar_cache=cache)

        self.assertEqual(outcomes["ndx-signal"]["high"], 4.99)
        self.assertEqual(outcomes["ndx-signal"]["current"], 4.50)
        self.assertEqual(outcomes["ndx-signal"]["current_time"], "2026-07-17T12:52:00-04:00")
        self.assertEqual(outcomes["ndx-signal"]["current_age_seconds"], 6)
        self.assertFalse(outcomes["ndx-signal"]["current_is_stale"])
        self.assertEqual(outcomes["spx-signal"]["high"], 5.25)
        self.assertEqual(outcomes["spx-signal"]["current"], 5.00)

    def test_option_outcomes_returns_row_error_without_bars_or_fallback(self):
        alpaca = MagicMock()
        alpaca.get_option_bars.side_effect = AlpacaApiError("option bars unavailable")
        alpaca.get_stock_bars.return_value = []

        outcomes = _option_outcomes(
            alpaca,
            [
                {
                    "id": "signal-3",
                    "symbol": "QQQ260710C00715000",
                    "date": "2026-07-10",
                    "timestamp_iso": "2026-07-10T14:30:00Z",
                    "underlying": "QQQ",
                }
            ],
        )

        self.assertIn("not cached in SQLite", outcomes["signal-3"]["error"])
        alpaca.get_option_bars.assert_not_called()

    def test_historical_option_prices_uses_latest_bar_close(self):
        alpaca = MagicMock()
        alpaca.provider_name = "databento"
        cache = MagicMock()
        cache.option_bars.return_value = {
            "QQQ260717C00720000": [
                {"t": "2026-07-13T14:30:00Z", "c": 2.1},
                {"t": "2026-07-13T15:00:00Z", "c": 2.85},
            ]
        }

        prices = _historical_option_prices(
            alpaca,
            ["QQQ260717C00720000"],
            "2026-07-13",
            "11:00:00",
            option_bar_cache=cache,
        )

        self.assertEqual(prices["QQQ260717C00720000"]["mid"], 2.85)
        self.assertEqual(prices["QQQ260717C00720000"]["source"], "SQLite historical option bar")
        alpaca.get_option_bars.assert_not_called()

def _handler(body: bytes = b""):
    handler = object.__new__(TradingBotWebHandler)
    handler.status = None
    handler.body = b""
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)

    def send_response(status):
        handler.status = status

    def send_header(_name, _value):
        return None

    def end_headers():
        return None

    class Writer:
        def write(self, body):
            handler.body += body

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    handler.wfile = Writer()
    return handler


if __name__ == "__main__":
    unittest.main()
