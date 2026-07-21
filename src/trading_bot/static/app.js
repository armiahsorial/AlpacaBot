const form = document.querySelector("#analysis-form");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const button = document.querySelector("#analyze-button");
const tickerChecklist = document.querySelector("#ticker-checklist");
const tickerPresetButtons = document.querySelectorAll("[data-ticker-group]");
const saveTickerGroupButton = document.querySelector("#save-ticker-group");
const tickerGroupName = document.querySelector("#ticker-group-name");
const savedTickerGroups = document.querySelector("#saved-ticker-groups");
const maxContractCostSelect = document.querySelector("#max-contract-cost");
const autoRefresh = document.querySelector("#auto-refresh");
const refreshSeconds = document.querySelector("#refresh-seconds");
const alpacaStatus = document.querySelector("#alpaca-status");
const refreshAlpacaButton = document.querySelector("#refresh-alpaca");
const refreshPositionsButton = document.querySelector("#refresh-positions");
const paperOrderForm = document.querySelector("#paper-order-form");
const loadBarButton = document.querySelector("#load-bar");
const loadContractsButton = document.querySelector("#load-contracts");
const liveUpdateButton = document.querySelector("#live-update");
const liveToggleButton = document.querySelector("#live-toggle");
const liveInterval = document.querySelector("#live-interval");
const liveStatus = document.querySelector("#live-status");
const replayDate = document.querySelector("#replay-date");
const replayTime = document.querySelector("#replay-time");
const replayClock = document.querySelector("#replay-clock");
const replayPlay = document.querySelector("#replay-play");
const replayRefresh = document.querySelector("#replay-refresh");
const cacheDayButton = document.querySelector("#cache-day");
const cacheStatus = document.querySelector("#cache-status");
const replayToday = document.querySelector("#replay-today");
const runDaySimulationButton = document.querySelector("#run-day-simulation");
const daySimulationStatus = document.querySelector("#day-simulation-status");
const stageBestPickButton = document.querySelector("#stage-best-pick");
const clearTradeHistoryButton = document.querySelector("#clear-trade-history");
const clearPaperLedgerButton = document.querySelector("#clear-paper-ledger");
const exportTradeHistoryButton = document.querySelector("#export-trade-history");
const exportTradeHistoryRangeButton = document.querySelector("#export-trade-history-range");
const historyStartDate = document.querySelector("#history-start-date");
const historyEndDate = document.querySelector("#history-end-date");
const historyTickers = document.querySelector("#history-tickers");
const historyExportStatus = document.querySelector("#history-export-status");
const tickerSelectionCount = document.querySelector("#ticker-selection-count");
const replayTimezone = document.querySelector("#replay-timezone");
const trackingOverviewRows = document.querySelector("#tracking-overview-rows");
const speedButtons = document.querySelectorAll("[data-speed]");
const barSymbol = document.querySelector("#bar-symbol");
const latestBar = document.querySelector("#latest-bar");
const metricTooltip = document.createElement("div");
metricTooltip.className = "metric-tooltip";
metricTooltip.setAttribute("role", "tooltip");
document.body.appendChild(metricTooltip);
let refreshTimer = null;
let liveTimer = null;
let liveClockTimer = null;
let ledgerPriceTimer = null;
let ledgerHighlightTimer = null;
let replayTimer = null;
let replayScrubTimer = null;
let replayRequestId = 0;
let replaySpeed = 1;
let replayClockRemainder = 0;
let lastAnalysis = null;
const latestAnalysisByTicker = new Map();
let isAnalysisRunning = false;
let isInspectingContract = false;
let isLiveLoading = false;
let isLedgerPriceLoading = false;
let isReplayLoading = false;
let replayAbortController = null;
let lastReplayFetchSecond = null;
let lastReplayFetchStartedAt = 0;
let currentBestPick = null;
let daySimulationRunning = false;
let daySimulationStopRequested = false;
let cachedTickersForReplay = new Set();
const replayOutcomeCache = new Map();
const displayedHistoryOutcomes = new Map();
const historicalLedgerOutcomeRequests = new Set();
const REPLAY_FETCH_STEP_SECONDS = 60;
const REPLAY_CLOCK_TICK_MS = 100;
const DAY_SIMULATION_STEP_SECONDS = 15 * 60;
// Completed-day playback advances from cached SQLite rows. Keep rendering
// rate-limited so rapid playback remains smooth even with large histories.
// independently of the selected playback speed.
const REPLAY_MIN_FETCH_INTERVAL_MS = 15000;
const TRADE_HISTORY_STORAGE_KEY = "tradingBot.tradePermissionHistory";
const PAPER_LEDGER_STORAGE_KEY = "tradingBot.paperSimulationLedger";
const TICKER_GROUPS_STORAGE_KEY = "tradingBot.tickerGroups";
const MAX_CONTRACT_COST_STORAGE_KEY = "tradingBot.maxContractCost";
const MAX_CONTRACT_DEFAULT_VERSION_KEY = "tradingBot.maxContractDefaultVersion";
const TRACKING_HISTORY_STORAGE_KEY = "tradingBot.trackedTickersByDate";
const DATABASE_MIGRATION_STORAGE_KEY = "tradingBot.sqliteMigrationVersion";
const OPTION_CONTRACT_MULTIPLIER = 100;
const EXIT_CONFIRMATION_REFRESHES = 2;
// Keep enough signals for multi-day exports instead of allowing one busy session
// to evict the previous day's history.
const MAX_TRADE_HISTORY_ITEMS = 2000;
const MAX_PAPER_LEDGER_ITEMS = 500;
const COMPACT_TRADE_HISTORY_ITEMS = 600;
const MAX_RECORDED_PERMISSION_CANDIDATES = 3;
const PAPER_LEDGER_DAILY_TRADE_LIMIT = 10;
const PAPER_LEDGER_MIN_SCORE = 100;
const PAPER_LEDGER_HIGHLIGHT_MS = 2 * 60 * 1000;
const MARKET_TIME_ZONE = "America/New_York";
let persistentStorageSyncTimer = null;
let persistentStorageSyncInFlight = false;
let persistentStorageSyncQueued = false;
let persistentStorageHydrating = false;
let historyGroupDate = "";
const openHistoryTickerGroups = new Set();
const persistentHistoryByDate = new Map();
const persistentHistoryRequests = new Map();
const historyOutcomeRequestVersions = new Map();

const fields = {
  tradePermission: document.querySelector("#trade-permission"),
  bias: document.querySelector("#bias"),
  confidence: document.querySelector("#confidence"),
  score: document.querySelector("#score"),
  spot: document.querySelector("#spot"),
  zeroGamma: document.querySelector("#zero-gamma"),
  technicalVwap: document.querySelector("#technical-vwap"),
  technicalSma50: document.querySelector("#technical-sma-50"),
  technicalSma200: document.querySelector("#technical-sma-200"),
  technicalFib200: document.querySelector("#technical-fib-200"),
  technicalLean: document.querySelector("#technical-lean"),
  technicalReasons: document.querySelector("#technical-reasons"),
  strikeChart: document.querySelector("#strike-chart"),
  action: document.querySelector("#action"),
  marketRegime: document.querySelector("#market-regime"),
  setup: document.querySelector("#setup"),
  entryTrigger: document.querySelector("#entry-trigger"),
  invalidation: document.querySelector("#invalidation"),
  targetZone: document.querySelector("#target-zone"),
  avoidZone: document.querySelector("#avoid-zone"),
  classicPositive: document.querySelector("#classic-positive"),
  classicNegative: document.querySelector("#classic-negative"),
  stateCall: document.querySelector("#state-call"),
  statePut: document.querySelector("#state-put"),
  distanceZero: document.querySelector("#distance-zero"),
  upsideRoom: document.querySelector("#upside-room"),
  downsideRoom: document.querySelector("#downside-room"),
  classicNet: document.querySelector("#classic-net"),
  stateNet: document.querySelector("#state-net"),
  classicChange: document.querySelector("#classic-change"),
  stateChange: document.querySelector("#state-change"),
  scoreBreakdown: document.querySelector("#score-breakdown"),
  reasons: document.querySelector("#reasons"),
  noTradePanel: document.querySelector("#no-trade-panel"),
  noTradeReasons: document.querySelector("#no-trade-reasons"),
  risk: document.querySelector("#risk"),
  alpacaAccountStatus: document.querySelector("#alpaca-account-status"),
  alpacaCash: document.querySelector("#alpaca-cash"),
  alpacaBuyingPower: document.querySelector("#alpaca-buying-power"),
  alpacaPortfolio: document.querySelector("#alpaca-portfolio"),
  positionsList: document.querySelector("#positions-list"),
  contractSummary: document.querySelector("#contract-summary"),
  contractList: document.querySelector("#contract-list"),
  bestPick: document.querySelector("#best-pick"),
  bestPickAction: document.querySelector("#best-pick-action"),
  bestPickContract: document.querySelector("#best-pick-contract"),
  bestPickReason: document.querySelector("#best-pick-reason"),
  bestPickExit: document.querySelector("#best-pick-exit"),
  tradeHistory: document.querySelector("#trade-history"),
  paperLedger: document.querySelector("#paper-ledger"),
  paperLedgerOpen: document.querySelector("#paper-ledger-open"),
  paperLedgerClosed: document.querySelector("#paper-ledger-closed"),
  lowerConfidenceLog: document.querySelector("#lower-confidence-log"),
  ledgerRealized: document.querySelector("#ledger-realized"),
  ledgerOpenPl: document.querySelector("#ledger-open-pl"),
  ledgerClosedCount: document.querySelector("#ledger-closed-count"),
  ledgerOpenCount: document.querySelector("#ledger-open-count"),
  ledgerWinRate: document.querySelector("#ledger-win-rate"),
  reportTotalTrades: document.querySelector("#report-total-trades"),
  reportWinRate: document.querySelector("#report-win-rate"),
  reportAverageWin: document.querySelector("#report-average-win"),
  reportAverageLoss: document.querySelector("#report-average-loss"),
  reportProfitFactor: document.querySelector("#report-profit-factor"),
  reportMaxDrawdown: document.querySelector("#report-max-drawdown"),
  reportBestTicker: document.querySelector("#report-best-ticker"),
  reportWorstTicker: document.querySelector("#report-worst-ticker"),
  reportProfitable: document.querySelector("#report-profitable"),
  multiTickerPanel: document.querySelector("#multi-ticker-panel"),
  multiTickerList: document.querySelector("#multi-ticker-list"),
};

function renderedContractContentExists() {
  return Boolean(fields.contractList?.querySelector(".ticker-contract-column, .contract-row"));
}

function captureViewportAnchor() {
  const viewportY = Math.min(Math.max(90, Math.round(window.innerHeight * 0.25)), window.innerHeight - 1);
  const startingElement = document.elementFromPoint(24, viewportY);
  const anchor = startingElement?.closest?.(
    "[data-scroll-key], #contract-list, #trade-history, #paper-ledger, #best-pick, #results"
  );
  if (!anchor) {
    return { scrollY: window.scrollY };
  }
  return {
    key: anchor.dataset.scrollKey || "",
    id: anchor.id || "",
    top: anchor.getBoundingClientRect().top,
    scrollY: window.scrollY,
  };
}

function findViewportAnchor(anchor) {
  if (!anchor) {
    return null;
  }
  if (anchor.key) {
    return [...document.querySelectorAll("[data-scroll-key]")]
      .find((element) => element.dataset.scrollKey === anchor.key) || null;
  }
  return anchor.id ? document.getElementById(anchor.id) : null;
}

function restoreViewportAnchor(anchor) {
  window.requestAnimationFrame(() => {
    const target = findViewportAnchor(anchor);
    if (target?.isConnected) {
      const delta = target.getBoundingClientRect().top - anchor.top;
      if (Math.abs(delta) > 1) {
        window.scrollBy(0, delta);
      }
      return;
    }
    if (Number.isFinite(anchor?.scrollY)) {
      window.scrollTo(window.scrollX, anchor.scrollY);
    }
  });
}

function withViewportAnchor(render) {
  const anchor = captureViewportAnchor();
  const result = render();
  restoreViewportAnchor(anchor);
  return result;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runAnalysis();
  scheduleRefresh();
});

form.addEventListener("change", (event) => {
  if (event.target?.matches?.("[data-ticker-checkbox], #ticker-group-name")) {
    return;
  }
  if (event.target === maxContractCostSelect) {
    localStorage.setItem(MAX_CONTRACT_COST_STORAGE_KEY, maxContractCostSelect.value);
    isInspectingContract = false;
  }
  runAnalysis();
  scheduleRefresh();
});

tickerChecklist?.addEventListener("change", () => {
  refreshForTickerSelection();
});

for (const presetButton of tickerPresetButtons) {
  presetButton.addEventListener("click", () => {
    setSelectedTickers(parseTickerGroupValue(presetButton.dataset.tickerGroup || ""));
    refreshForTickerSelection();
  });
}

saveTickerGroupButton?.addEventListener("click", () => {
  saveCurrentTickerGroup();
});

autoRefresh.addEventListener("change", () => {
  if (autoRefresh.checked) {
    isInspectingContract = false;
  }
  scheduleRefresh();
});

refreshSeconds.addEventListener("change", () => {
  scheduleRefresh();
});

refreshAlpacaButton?.addEventListener("click", () => {
  refreshAlpaca();
});

refreshPositionsButton?.addEventListener("click", () => {
  loadPositions();
});

loadBarButton?.addEventListener("click", () => {
  loadLatestBar();
});

loadContractsButton?.addEventListener("click", () => {
  stopLiveMode();
  isInspectingContract = false;
  loadOptionReplay();
});

liveUpdateButton?.addEventListener("click", () => {
  runLiveUpdate({ manual: true });
});

liveToggleButton.addEventListener("click", () => {
  toggleLiveMode();
});

liveInterval.addEventListener("change", () => {
  if (liveTimer !== null) {
    startLiveMode();
  }
});

replayDate.addEventListener("change", () => {
  stopLiveMode();
  applyHostMarketWindow(replayDate.value);
  syncHistoryExportDatesToReplayDate();
  renderTrackingOverview();
  renderTradeHistory();
  ensureHistoricalDateLoaded(replayDate.value);
  refreshCacheStatus();
  loadOptionReplay();
});

replayTime.addEventListener("input", () => {
  updateReplayClock();
  renderTradeHistory({ refreshData: false });
  scheduleReplayScrubRefresh();
});

replayTime.addEventListener("change", async () => {
  clearReplayScrubTimer();
  stopLiveMode();
  renderTradeHistory();
  await loadOptionReplay({ force: true });
});

replayClock.addEventListener("change", async () => {
  const typedSeconds = parseClock(replayClock.value);
  if (typedSeconds === null) {
    updateReplayClock();
    return;
  }
  stopLiveMode();
  stopReplay();
  clearReplayScrubTimer();
  replayTime.value = String(Math.min(
    Math.max(typedSeconds, Number(replayTime.min)),
    Number(replayTime.max)
  ));
  lastReplayFetchSecond = null;
  updateReplayClock();
  renderTradeHistory();
  await loadOptionReplay({ force: true });
});

replayClock.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    replayClock.blur();
  }
});

replayPlay.addEventListener("click", () => {
  if (liveTimer !== null) {
    setStatus("Live Mode is already playing. Use Stop Live to leave live mode.", false);
    return;
  }
  toggleReplay();
});

replayRefresh.addEventListener("click", () => {
  stopLiveMode();
  replayOutcomeCache.clear();
  loadOptionReplay({ force: true });
});

cacheDayButton?.addEventListener("click", () => {
  cacheSelectedDay();
});

replayToday.addEventListener("click", () => {
  jumpToTodayNow();
});

runDaySimulationButton?.addEventListener("click", () => {
  if (daySimulationRunning) {
    daySimulationStopRequested = true;
    setDaySimulationStatus("Stopping after the current replay point...", false);
    return;
  }
  runDaySimulation();
});

stageBestPickButton?.addEventListener("click", () => {
  if (!currentBestPick) {
    return;
  }
  stageCandidate(currentBestPick.candidate, currentBestPick.entryPrice, currentBestPick.message);
});

clearTradeHistoryButton.addEventListener("click", () => {
  clearTradeHistoryForSelectedDay();
  renderTradeHistory();
});

clearPaperLedgerButton?.addEventListener("click", () => {
  clearPaperLedgerForSelectedDay();
  renderPaperLedger();
});

fields.paperLedger?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-ledger-ack]");
  if (!button) {
    return;
  }
  acknowledgePaperLedgerHighlight(button.dataset.ledgerAck, button.dataset.ledgerState);
});

exportTradeHistoryButton?.addEventListener("click", async () => {
  await downloadTradeHistoryForSelectedDay();
});

exportTradeHistoryRangeButton?.addEventListener("click", async () => {
  exportTradeHistoryRangeButton.disabled = true;
  try {
    await downloadTradeHistoryForRange();
  } finally {
    exportTradeHistoryRangeButton.disabled = false;
  }
});

for (const control of [historyStartDate, historyEndDate, historyTickers]) {
  control?.addEventListener("input", updateHistoryRangeCount);
  control?.addEventListener("change", updateHistoryRangeCount);
}

document.addEventListener("pointerover", (event) => {
  const target = event.target.closest(".info-dot");
  if (target) {
    showMetricTooltip(target);
  }
});

document.addEventListener("pointerout", (event) => {
  const target = event.target.closest(".info-dot");
  if (target) {
    hideMetricTooltip();
  }
});

document.addEventListener("focusin", (event) => {
  const target = event.target.closest(".info-dot");
  if (target) {
    showMetricTooltip(target);
  }
});

document.addEventListener("focusout", (event) => {
  const target = event.target.closest(".info-dot");
  if (target) {
    hideMetricTooltip();
  }
});

window.addEventListener("scroll", hideMetricTooltip, { passive: true });
window.addEventListener("resize", hideMetricTooltip);

for (const speedButton of speedButtons) {
  speedButton.addEventListener("click", () => {
    replaySpeed = Number(speedButton.dataset.speed || 10);
    for (const button of speedButtons) {
      button.classList.toggle("active", button === speedButton);
    }
  });
}

paperOrderForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitPaperOrder();
});

async function runAnalysis({ isRefresh = false } = {}) {
  if (isAnalysisRunning) {
    return;
  }

  isAnalysisRunning = true;
  const { period } = getFormValues();
  const tickers = getSelectedTickers();
  const primaryTicker = tickers[0] || "SPX";
  updateTickerSelectionCount();
  if (!replayDate.value || replayDate.value === currentHostDate()) {
    recordTrackedTickers(currentHostDate(), tickers);
  }

  setStatus(isRefresh ? `Refreshing ${tickers.join(", ")} GEX data...` : `Pulling ${tickers.join(", ")} GEX data...`, false);
  if (button) {
    button.disabled = true;
  }

  try {
    const analyses = await Promise.all(tickers.map((ticker) => loadTickerAnalysis(ticker, period)));
    rememberTickerAnalyses(analyses);
    renderMultiTickerSummary(analyses);
    const primaryResult = analyses.find((result) => result.ticker === primaryTicker && result.payload) || analyses.find((result) => result.payload);
    if (!primaryResult) {
      throw new Error(analyses.map((result) => `${result.ticker}: ${result.error}`).join(" | ") || "Analysis failed.");
    }
    lastAnalysis = primaryResult.payload;
    renderAnalysis(primaryResult.payload);
    if (!isRefresh && !isInspectingContract) {
      await loadOptionRecommendation();
    }
    refreshVisibleTradeHistoryPrices();
    const failedCount = analyses.filter((result) => result.error).length;
    const partial = failedCount > 0 ? ` ${failedCount} ticker${failedCount === 1 ? "" : "s"} failed.` : "";
    setStatus(`Updated ${tickers.join(", ")} ${period} at ${new Date().toLocaleTimeString()}.${partial}`, failedCount > 0);
  } catch (error) {
    resultsEl.classList.add("hidden");
    setStatus(error.message, true);
  } finally {
    if (button) {
      button.disabled = false;
    }
    isAnalysisRunning = false;
  }
}

async function loadTickerAnalysis(ticker, period) {
  try {
    const query = new URLSearchParams({ ticker, period });
    const payload = await getJson(`/api/analyze?${query.toString()}`);
    return { ticker, payload };
  } catch (error) {
    return { ticker, error: error.message || "Analysis failed." };
  }
}

function renderMultiTickerSummary(results) {
  if (!fields.multiTickerPanel || !fields.multiTickerList) {
    return;
  }

  if (results.length <= 1) {
    fields.multiTickerPanel.classList.add("hidden");
    fields.multiTickerList.innerHTML = "";
    return;
  }

  fields.multiTickerPanel.classList.remove("hidden");
  fields.multiTickerList.innerHTML = "";
  for (const result of results) {
    const card = document.createElement("article");
    if (result.error) {
      card.className = "multi-ticker-card error";
      card.innerHTML = `
        <strong>${result.ticker}</strong>
        <span>Unavailable</span>
        <em>${result.error}</em>
      `;
      fields.multiTickerList.appendChild(card);
      continue;
    }

    const analysis = result.payload;
    card.className = `multi-ticker-card permission-${permissionClass(analysis.trade_permission)}`;
    card.innerHTML = `
      <strong>${result.ticker}</strong>
      <span>${analysis.trade_permission}</span>
      <span>${analysis.bias}</span>
      <span>score ${formatOptionalNumber(analysis.score)}</span>
      <span>spot ${formatOptionalNumber(analysis.spot)}</span>
    `;
    fields.multiTickerList.appendChild(card);
  }
}

function rememberTickerAnalyses(results) {
  for (const result of results || []) {
    const analysis = result?.payload?.analysis || result?.payload;
    const ticker = String(result?.ticker || analysis?.ticker || "").toUpperCase();
    if (ticker && analysis && !result?.error) {
      latestAnalysisByTicker.set(ticker, analysis);
    }
  }
}

async function runLiveUpdate({ manual = false } = {}) {
  if (isLiveLoading) {
    return;
  }

  stopReplay();
  isLiveLoading = true;
  isInspectingContract = false;
  liveStatus.textContent = manual ? "Refreshing live contracts once..." : "Auto Live refreshing contracts...";
  liveStatus.classList.remove("error");

  try {
    await loadOptionRecommendation({ source: "live" });
    refreshVisibleTradeHistoryPrices();
    liveStatus.textContent = manual
      ? `One live refresh completed at ${new Date().toLocaleTimeString()}.`
      : `Auto Live updated at ${new Date().toLocaleTimeString()}.`;
  } catch (error) {
    liveStatus.textContent = error.message;
    liveStatus.classList.add("error");
  } finally {
    isLiveLoading = false;
  }
}

function startLiveMode() {
  stopLiveMode();
  stopReplay();
  if (refreshTimer !== null) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  const seconds = Math.max(15, Number(liveInterval.value || 15));
  liveToggleButton.textContent = "Stop Auto Live";
  liveStatus.textContent = `Auto Live is on. GEX decisions refresh every ${seconds} seconds; open ledger prices stream every second.`;
  syncLiveClock();
  liveClockTimer = setInterval(syncLiveClock, 1000);
  runLiveUpdate();
  liveTimer = setInterval(() => {
    runLiveUpdate();
  }, seconds * 1000);
  refreshOpenPaperLedgerPrices();
  ledgerPriceTimer = setInterval(refreshOpenPaperLedgerPrices, 1000);
  updatePlaybackButton();
}

function stopLiveMode() {
  if (liveTimer !== null) {
    clearInterval(liveTimer);
    liveTimer = null;
  }
  if (liveClockTimer !== null) {
    clearInterval(liveClockTimer);
    liveClockTimer = null;
  }
  if (ledgerPriceTimer !== null) {
    clearInterval(ledgerPriceTimer);
    ledgerPriceTimer = null;
  }
  liveToggleButton.textContent = "Start Auto Live";
  updatePlaybackButton();
  if (!isLiveLoading) {
    liveStatus.textContent = "Auto Live is off. Historical replay remains available.";
  }
}

async function refreshOpenPaperLedgerPrices() {
  if (isLedgerPriceLoading || replayDate.value !== currentHostDate()) {
    return;
  }
  const symbols = [...new Set(loadPaperLedger()
    .filter((trade) => trade.status !== "closed" && paperLedgerDay(trade) === currentHostDate())
    .map((trade) => String(trade.symbol || "").toUpperCase())
    .filter(Boolean))]
    .slice(0, PAPER_LEDGER_DAILY_TRADE_LIMIT);
  if (symbols.length === 0) {
    return;
  }
  isLedgerPriceLoading = true;
  try {
    const query = new URLSearchParams({ symbols: symbols.join(",") });
    const payload = await getJson(`/api/options/stream-prices?${query.toString()}`);
    updatePaperLedgerPrices(payload.prices || {}, null, { evaluateExit: false });
  } catch (error) {
    if (/require Databento live streaming/i.test(String(error?.message || error))) {
      clearInterval(ledgerPriceTimer);
      ledgerPriceTimer = null;
    }
  } finally {
    isLedgerPriceLoading = false;
  }
}

function toggleLiveMode() {
  if (liveTimer !== null) {
    stopLiveMode();
    return;
  }
  startLiveMode();
}

function syncLiveClock() {
  const market = currentHostMarketSnapshot();
  replayDate.value = market.date;
  applyHostMarketWindow(market.date);
  replayTime.value = String(market.clampedSeconds);
  updateReplayClock();
}

function renderAnalysis(analysis) {
  fields.tradePermission.textContent = analysis.trade_permission;
  fields.bias.textContent = analysis.bias;
  fields.confidence.textContent = analysis.confidence;
  fields.score.textContent = `${analysis.score}`;
  fields.spot.textContent = formatNumber(analysis.spot);
  fields.zeroGamma.textContent = formatNumber(analysis.zero_gamma);
  fields.action.textContent = analysis.action;
  fields.marketRegime.textContent = analysis.market_regime;
  fields.setup.textContent = analysis.setup;
  fields.entryTrigger.textContent = analysis.entry_trigger;
  fields.invalidation.textContent = analysis.invalidation;
  fields.targetZone.textContent = analysis.target_zone;
  fields.avoidZone.textContent = analysis.avoid_zone;
  fields.classicPositive.textContent = formatNumber(analysis.classic_major_positive);
  fields.classicNegative.textContent = formatNumber(analysis.classic_major_negative);
  fields.stateCall.textContent = formatNumber(analysis.state_call_gamma_node);
  fields.statePut.textContent = formatNumber(analysis.state_put_gamma_node);
  fields.distanceZero.textContent = formatOptionalNumber(analysis.distance_to_zero_gamma);
  fields.upsideRoom.textContent = formatOptionalNumber(analysis.upside_room);
  fields.downsideRoom.textContent = formatOptionalNumber(analysis.downside_room);
  fields.classicNet.textContent = formatNumber(analysis.classic_net_gex);
  fields.stateNet.textContent = formatNumber(analysis.state_net_imbalance);
  fields.classicChange.textContent = formatChange(analysis.classic_thirty_min_change);
  fields.stateChange.textContent = formatChange(analysis.state_thirty_min_change);
  fields.risk.textContent = analysis.risk_note;
  renderTechnicals(analysis.technicals);
  renderStrikeChart(analysis);

  renderList(fields.reasons, analysis.reasons);
  renderList(fields.scoreBreakdown, analysis.score_breakdown);

  if (analysis.no_trade_reasons.length > 0) {
    renderList(fields.noTradeReasons, analysis.no_trade_reasons);
    fields.noTradePanel.classList.remove("hidden");
  } else {
    fields.noTradeReasons.innerHTML = "";
    fields.noTradePanel.classList.add("hidden");
  }

  resultsEl.classList.remove("hidden");
}

function renderTechnicals(technicals) {
  if (!technicals) {
    fields.technicalVwap.textContent = "-";
    fields.technicalSma50.textContent = "-";
    fields.technicalSma200.textContent = "-";
    fields.technicalFib200.textContent = "-";
    fields.technicalLean.textContent = "Unavailable";
    fields.technicalReasons.innerHTML = "";
    return;
  }

  fields.technicalVwap.textContent = formatOptionalNumber(technicals.vwap);
  fields.technicalSma50.textContent = formatOptionalNumber(technicals.sma_50);
  fields.technicalSma200.textContent = formatOptionalNumber(technicals.sma_200);
  fields.technicalFib200.textContent = formatFibAlignment(technicals.fibonacci_near_sma_200);
  fields.technicalLean.textContent = technicalLeanLabel(technicals.score_adjustment);
  renderList(fields.technicalReasons, [...(technicals.reasons || []), ...(technicals.warnings || [])]);
}

function formatFibAlignment(alignment) {
  if (!alignment) {
    return "-";
  }
  const label = alignment.label || "Fib";
  const level = formatOptionalNumber(alignment.level);
  const distance = formatOptionalNumber(alignment.distance);
  return `${label} at ${level} (${distance} from 200 MA)`;
}

function technicalLeanLabel(adjustment) {
  if (adjustment >= 2) {
    return "Bullish confirmation";
  }
  if (adjustment === 1) {
    return "Slight bullish support";
  }
  if (adjustment <= -2) {
    return "Bearish confirmation";
  }
  if (adjustment === -1) {
    return "Slight bearish pressure";
  }
  return "Mixed / neutral";
}

function getFormValues() {
  const data = new FormData(form);
  const tickers = getSelectedTickers();
  return {
    ticker: tickers[0] || "SPX",
    period: String(data.get("period") || "zero"),
  };
}

function getSelectedTickers() {
  const selected = Array.from(document.querySelectorAll("[data-ticker-checkbox]:checked"))
    .map((checkbox) => checkbox.value.trim().toUpperCase())
    .filter(Boolean);
  return selected.length > 0 ? [...new Set(selected)] : ["NDX", "SPX"];
}

function getMaxContractCost() {
  const value = Number(maxContractCostSelect?.value || 0);
  return value > 0 ? value : null;
}

function addContractCostLimit(query) {
  const maxContractCost = getMaxContractCost();
  if (maxContractCost !== null) {
    query.set("max_contract_cost", String(maxContractCost));
  }
  return query;
}

function initializeMaxContractCost() {
  if (!maxContractCostSelect) {
    return;
  }
  if (localStorage.getItem(MAX_CONTRACT_DEFAULT_VERSION_KEY) !== "1000-v1") {
    localStorage.setItem(MAX_CONTRACT_COST_STORAGE_KEY, "1000");
    localStorage.setItem(MAX_CONTRACT_DEFAULT_VERSION_KEY, "1000-v1");
  }
  const saved = localStorage.getItem(MAX_CONTRACT_COST_STORAGE_KEY) || "1000";
  if ([...maxContractCostSelect.options].some((option) => option.value === saved)) {
    maxContractCostSelect.value = saved;
  }
}

function setSelectedTickers(tickers) {
  const selected = new Set((tickers.length > 0 ? tickers : ["NDX", "SPX"]).map((ticker) => ticker.toUpperCase()));
  for (const checkbox of document.querySelectorAll("[data-ticker-checkbox]")) {
    checkbox.checked = selected.has(checkbox.value.toUpperCase());
  }
  updateTickerSelectionCount();
}

function updateTickerSelectionCount() {
  if (!tickerSelectionCount) {
    return;
  }
  const count = getSelectedTickers().length;
  tickerSelectionCount.textContent = `${count} selected`;
}

function loadTrackedTickerHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(TRACKING_HISTORY_STORAGE_KEY) || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (error) {
    return {};
  }
}

function recordTrackedTickers(dateValue, tickers) {
  if (!dateValue || !Array.isArray(tickers) || tickers.length === 0) {
    return;
  }
  const history = loadTrackedTickerHistory();
  const merged = new Set([...(history[dateValue] || []), ...tickers].map((ticker) => String(ticker).toUpperCase()));
  history[dateValue] = [...merged].sort();
  try {
    localStorage.setItem(TRACKING_HISTORY_STORAGE_KEY, JSON.stringify(history));
  } catch (error) {
    // Trade history remains untouched if the browser cannot store this optional index.
  }
  schedulePersistentStorageSync();
  renderTrackingOverview();
}

function trackedTickerOverview() {
  const byDate = new Map();
  const add = (dateValue, ticker) => {
    const normalized = String(ticker || "").trim().toUpperCase();
    if (!dateValue || !normalized) {
      return;
    }
    if (!byDate.has(dateValue)) {
      byDate.set(dateValue, new Set());
    }
    byDate.get(dateValue).add(normalized);
  };

  for (const [dateValue, tickers] of Object.entries(loadTrackedTickerHistory())) {
    for (const ticker of Array.isArray(tickers) ? tickers : []) {
      add(dateValue, ticker);
    }
  }
  for (const item of loadTradeHistory()) {
    add(historyItemDate(item), item.ticker || item.underlying || contractUnderlying(item));
  }
  for (const trade of loadPaperLedger()) {
    add(paperLedgerDay(trade), trade.ticker || trade.underlying || contractUnderlying(trade));
  }
  return [...byDate.entries()]
    .map(([dateValue, tickers]) => ({ date: dateValue, tickers: [...tickers].sort() }))
    .sort((a, b) => b.date.localeCompare(a.date));
}

function renderTrackingOverview() {
  if (!trackingOverviewRows) {
    return;
  }
  const rows = trackedTickerOverview();
  if (rows.length === 0) {
    trackingOverviewRows.innerHTML = `
      <div class="tracking-overview-row"><span>${escapeHtml(replayDate.value || currentHostDate())}</span><span>No saved tracking activity yet</span></div>
    `;
    return;
  }
  trackingOverviewRows.innerHTML = rows.slice(0, 10).map((row) => `
    <div class="tracking-overview-row${row.date === replayDate.value ? " active" : ""}" role="row">
      <span role="cell">${escapeHtml(formatContractDate(row.date))}</span>
      <span role="cell">${escapeHtml(row.tickers.join(", "))}</span>
    </div>
  `).join("");
}

async function refreshForTickerSelection() {
  isInspectingContract = false;
  lastReplayFetchSecond = null;
  updateTickerSelectionCount();
  if (!replayDate.value || replayDate.value === currentHostDate()) {
    recordTrackedTickers(currentHostDate(), getSelectedTickers());
  }
  renderTradeHistory();
  if (replayDate.value && !selectedReplayUsesLiveData()) {
    stopLiveMode();
    await loadOptionReplay({ force: true });
  } else {
    await runAnalysis();
  }
  scheduleRefresh();
}

function parseTickerGroupValue(value) {
  return [...new Set(
    String(value || "")
      .split(",")
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean)
  )];
}

function saveCurrentTickerGroup() {
  const tickers = getSelectedTickers();
  const name = String(tickerGroupName?.value || tickers.join(" + ")).trim();
  if (!name || tickers.length === 0) {
    setStatus("Pick at least one ticker and name the group first.", true);
    return;
  }
  const groups = loadTickerGroups().filter((group) => group.name.toLowerCase() !== name.toLowerCase());
  groups.push({ name, tickers });
  saveTickerGroups(groups);
  if (tickerGroupName) {
    tickerGroupName.value = "";
  }
  renderTickerGroups();
  setStatus(`Saved ticker group ${name}: ${tickers.join(", ")}.`, false);
}

function loadTickerGroups() {
  try {
    const raw = localStorage.getItem(TICKER_GROUPS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((group) => group?.name && Array.isArray(group.tickers))
      : [];
  } catch (_error) {
    return [];
  }
}

function saveTickerGroups(groups) {
  try {
    localStorage.setItem(TICKER_GROUPS_STORAGE_KEY, JSON.stringify(groups));
  } catch (_error) {
    setStatus("Ticker group could not be saved in this browser.", true);
  }
}

function renderTickerGroups() {
  if (!savedTickerGroups) {
    return;
  }
  const groups = loadTickerGroups();
  if (groups.length === 0) {
    savedTickerGroups.innerHTML = "";
    return;
  }
  savedTickerGroups.innerHTML = groups
    .map((group, index) => `
      <span class="saved-ticker-group">
        <button type="button" data-saved-ticker-group="${index}">${escapeHtml(group.name)}</button>
        <button type="button" data-delete-ticker-group="${index}" aria-label="Delete ${escapeAttribute(group.name)}">x</button>
      </span>
    `)
    .join("");
  for (const button of savedTickerGroups.querySelectorAll("[data-saved-ticker-group]")) {
    button.addEventListener("click", () => {
      const group = loadTickerGroups()[Number(button.dataset.savedTickerGroup)];
      if (!group) {
        return;
      }
      setSelectedTickers(group.tickers);
      refreshForTickerSelection();
    });
  }
  for (const button of savedTickerGroups.querySelectorAll("[data-delete-ticker-group]")) {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.deleteTickerGroup);
      const nextGroups = loadTickerGroups().filter((_group, groupIndex) => groupIndex !== index);
      saveTickerGroups(nextGroups);
      renderTickerGroups();
    });
  }
}

function permissionClass(permission) {
  const normalized = String(permission || "").toLowerCase();
  if (normalized.includes("no")) {
    return "no-trade";
  }
  if (normalized.includes("trade")) {
    return "trade";
  }
  return "watch";
}

function scheduleRefresh() {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }

  // Auto Live recommendations already include a full GEX analysis. Running the
  // separate analysis timer at the same time would duplicate every GEX call.
  if (!autoRefresh.checked || !currentHostMarketSnapshot().isOpen || liveTimer !== null) {
    return;
  }

  const seconds = Number(refreshSeconds.value || 1);
  refreshTimer = setInterval(() => {
    runAnalysis({ isRefresh: true });
  }, seconds * 1000);
}

initializeReplayControls();
initializeTradeHistoryExportControls();
renderTickerGroups();
initializeMaxContractCost();
updateTickerSelectionCount();
autoRefresh.checked = true;
initializeMarketMode();
refreshCacheStatus();
scheduleRefresh();
renderTradeHistory();
initializePersistentStorage();

function renderStrikeChart(analysis) {
  const points = [
    { key: "state-put", label: "State put", shortLabel: "State put", value: analysis.state_put_gamma_node },
    { key: "put", label: "Classic negative", shortLabel: "Classic neg", value: analysis.classic_major_negative },
    { key: "spot", label: "Spot", shortLabel: "Spot", value: analysis.spot },
    { key: "zero", label: "Zero gamma", shortLabel: "Zero gamma", value: analysis.zero_gamma },
    { key: "classic-call", label: "Classic positive", shortLabel: "Classic pos", value: analysis.classic_major_positive },
    { key: "call", label: "State call", shortLabel: "State call", value: analysis.state_call_gamma_node },
  ].filter((point) => Number.isFinite(Number(point.value)));

  if (points.length === 0) {
    fields.strikeChart.innerHTML = "";
    return;
  }

  const values = points.map((point) => Number(point.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  const padding = Math.max(span * 0.08, 5);
  const axisMin = min - padding;
  const axisMax = max + padding;
  const axisSpan = axisMax - axisMin;
  const positionedPoints = assignMarkerRows(
    points
      .map((point) => ({
        ...point,
        left: ((Number(point.value) - axisMin) / axisSpan) * 100,
      }))
      .sort((a, b) => a.left - b.left)
  );

  const zoneHtml = [
    zoneBand("put-zone", analysis.classic_major_negative, analysis.state_put_gamma_node, axisMin, axisMax, "Put pressure"),
    zoneBand("call-zone", analysis.state_call_gamma_node, analysis.classic_major_positive, axisMin, axisMax, "Call pressure"),
  ].join("");

  const markerHtml = positionedPoints
    .map((point) => {
      const edgeClass = point.left < 8 ? "edge-left" : point.left > 92 ? "edge-right" : "";
      return `
        <div class="rail-marker marker-${point.key}" style="--x: ${point.left}%">
          <span class="marker-pin"></span>
        </div>
        <div class="marker-card marker-${point.key} marker-row-${point.row} ${edgeClass}" style="--x: ${point.left}%">
          <span>${point.shortLabel}</span>
          <strong>${formatNumber(point.value)}</strong>
        </div>
      `;
    })
    .join("");

  fields.strikeChart.innerHTML = `
    <div class="axis">
      <span>${formatNumber(axisMin)}</span>
      <span>${formatNumber(axisMax)}</span>
    </div>
    <div class="strike-rail">
      ${zoneHtml}
      <div class="rail-baseline"></div>
      ${markerHtml}
    </div>
    <div class="trade-pointers">
      <div class="pointer call-pointer">
        <span>Calls</span>
        <strong>${callPointerText(analysis)}</strong>
      </div>
      <div class="pointer put-pointer">
        <span>Puts</span>
        <strong>${putPointerText(analysis)}</strong>
      </div>
    </div>
  `;
}

function assignMarkerRows(points) {
  const rows = [-Infinity, -Infinity, -Infinity, -Infinity];
  const minimumGap = 13;

  return points.map((point) => {
    let row = rows.findIndex((lastLeft) => point.left - lastLeft >= minimumGap);
    if (row === -1) {
      row = rows.indexOf(Math.min(...rows));
    }
    rows[row] = point.left;
    return { ...point, row };
  });
}

function zoneBand(className, firstValue, secondValue, axisMin, axisMax, label) {
  if (!Number.isFinite(Number(firstValue)) || !Number.isFinite(Number(secondValue))) {
    return "";
  }

  const start = Math.min(Number(firstValue), Number(secondValue));
  const end = Math.max(Number(firstValue), Number(secondValue));
  const left = Math.max(0, ((start - axisMin) / (axisMax - axisMin)) * 100);
  const right = Math.min(100, ((end - axisMin) / (axisMax - axisMin)) * 100);
  const width = Math.max(right - left, 0.8);

  return `<div class="zone-band ${className}" style="left: ${left}%; width: ${width}%"><span>${label}</span></div>`;
}

function callPointerText(analysis) {
  if (analysis.bias === "bullish" || analysis.bias === "neutral-bullish") {
    return `Watch hold above ${formatNumber(analysis.zero_gamma)}; avoid chasing into ${formatNumber(analysis.classic_major_positive)}-${formatNumber(analysis.state_call_gamma_node)}.`;
  }
  return `No call buy zone unless price reclaims ${formatNumber(analysis.zero_gamma)} with improving state imbalance.`;
}

function putPointerText(analysis) {
  if (analysis.bias === "bearish" || analysis.bias === "neutral-bearish") {
    return `Watch rejection below ${formatNumber(analysis.zero_gamma)}; target pressure near ${formatNumber(analysis.classic_major_negative)}-${formatNumber(analysis.state_put_gamma_node)}.`;
  }
  return `No put buy zone unless price loses ${formatNumber(analysis.zero_gamma)} or the put node near ${formatNumber(analysis.state_put_gamma_node)}.`;
}

function formatNumber(value) {
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  });
}

function formatOptionalNumber(value) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  return formatNumber(value);
}

function formatChange(pair) {
  const [strike, value] = pair;
  return `${formatNumber(value)} at ${formatNumber(strike)}`;
}

function renderList(element, items) {
  element.innerHTML = "";
  for (const text of items) {
    const item = document.createElement("li");
    item.textContent = text;
    element.appendChild(item);
  }
}

async function refreshAlpaca() {
  if (!alpacaStatus && !fields.positionsList) {
    return;
  }
  await Promise.all([loadAccount(), loadPositions()]);
}

async function loadAccount() {
  if (!fields.alpacaAccountStatus) {
    return;
  }
  setAlpacaStatus("Loading Alpaca account...", false);
  try {
    const account = await getJson("/api/alpaca/account");
    fields.alpacaAccountStatus.textContent = account.status || "-";
    fields.alpacaCash.textContent = formatCurrency(account.cash);
    fields.alpacaBuyingPower.textContent = formatCurrency(account.buying_power);
    fields.alpacaPortfolio.textContent = formatCurrency(account.portfolio_value);
    setAlpacaStatus("Alpaca paper account connected.", false);
  } catch (error) {
    setAlpacaStatus(error.message, true);
  }
}

async function loadPositions() {
  if (!fields.positionsList) {
    return;
  }
  try {
    const payload = await getJson("/api/alpaca/positions");
    const positions = payload.positions || [];
    if (positions.length === 0) {
      fields.positionsList.textContent = "No open paper positions.";
      return;
    }
    fields.positionsList.innerHTML = positions
      .map((position) => {
        const value = formatCurrency(position.market_value);
        const pl = formatCurrency(position.unrealized_pl);
        return `<div><strong>${position.symbol}</strong><span>${position.qty} sh</span><span>${value}</span><span>${pl}</span></div>`;
      })
      .join("");
  } catch (error) {
    fields.positionsList.textContent = error.message;
  }
}

async function loadLatestBar() {
  if (!barSymbol || !latestBar) {
    return;
  }
  const symbol = String(barSymbol.value || "SPY").trim().toUpperCase();
  latestBar.textContent = "Loading...";
  try {
    const payload = await getJson(`/api/alpaca/latest-bar?symbol=${encodeURIComponent(symbol)}`);
    latestBar.textContent = JSON.stringify(payload.bars?.[symbol] || payload, null, 2);
  } catch (error) {
    latestBar.textContent = error.message;
  }
}

async function submitPaperOrder() {
  if (!paperOrderForm) {
    return;
  }
  const data = new FormData(paperOrderForm);
  const payload = {
    symbol: String(data.get("symbol") || "").trim().toUpperCase(),
    side: String(data.get("side") || "buy"),
    qty: optionalNumber(data.get("qty")),
    type: String(data.get("type") || "market"),
    time_in_force: "day",
    limit_price: optionalNumber(data.get("limit_price")),
  };

  setAlpacaStatus("Submitting paper order...", false);
  try {
    const order = await postJson("/api/alpaca/orders", payload);
    setAlpacaStatus(`Submitted ${order.side} ${order.qty || order.notional} ${order.symbol}: ${order.status}.`, false);
    await Promise.all([loadAccount(), loadPositions()]);
  } catch (error) {
    setAlpacaStatus(error.message, true);
  }
}

async function loadOptionRecommendation({ source = "manual" } = {}) {
  const { period } = getFormValues();
  const tickers = getSelectedTickers();
  fields.contractSummary.textContent = `Scanning Alpaca options for ${tickers.join(", ")}...`;
  fields.contractSummary.classList.remove("error");
  fields.contractList.classList.add("is-refreshing");
  if (!renderedContractContentExists()) {
    fields.contractList.textContent = "Loading contract candidates...";
  }

  try {
    const payloads = [];
    const errors = [];
    for (const ticker of tickers) {
      try {
        const query = addContractCostLimit(new URLSearchParams({
          ticker,
          period,
          max_expiration_days: "14",
          limit: "3",
        }));
        payloads.push(await getJson(`/api/options/recommend?${query.toString()}`));
      } catch (error) {
        errors.push({ ticker, message: error.message || "Options request failed." });
      }
    }

    if (payloads.length > 0) {
      renderOptionRecommendations(payloads, errors);
      return;
    }

    const message = errors.map((error) => `${error.ticker}: ${error.message}`).join(" | ") || "Options scan failed.";
    fields.contractSummary.textContent = message;
    fields.contractSummary.classList.add("error");
    if (!renderedContractContentExists()) {
      fields.contractList.textContent = message;
      resetBestPick();
    }
    if (source === "live") {
      throw new Error(message);
    }
  } finally {
    fields.contractList.classList.remove("is-refreshing");
  }
}

async function loadOptionReplaysForTickers(tickers, period, { signal } = {}) {
  const payloads = [];
  const errors = [];
  for (const ticker of tickers) {
    try {
      const query = addContractCostLimit(new URLSearchParams({
        ticker,
        period,
        date: replayDate.value,
        time: getReplayMarketClock(),
        max_expiration_days: "14",
        limit: "3",
        local_only: "1",
      }));
      payloads.push(await getJsonWithTimeout(`/api/options/replay?${query.toString()}`, {
        signal,
        timeoutMs: 90000,
      }));
    } catch (error) {
      if (error.name === "AbortError") {
        throw error;
      }
      errors.push({ ticker, message: error.message || "Replay request failed." });
    }
  }
  return { payloads, errors };
}

function replayErrorMessage(errors) {
  return errors.map((error) => `${error.ticker}: ${error.message}`).join(" | ") || "Replay request failed.";
}

function showReplayError(error) {
  if (error.name === "AbortError") {
    fields.contractSummary.textContent = "Previous replay request canceled. Press Reload SQLite to try again.";
  } else {
    fields.contractSummary.textContent = error.message;
    fields.contractSummary.classList.add("error");
    resetBestPick();
  }
}

async function loadOptionReplay({ force = false, refreshHistory = true } = {}) {
  updateReplayClock();
  if (selectedReplayUsesLiveData()) {
    stopReplay();
    isInspectingContract = false;
    fields.contractSummary.classList.remove("error");
    fields.contractSummary.textContent = "Today uses live GEX and Alpaca data instead of historical replay files.";
    await runAnalysis();
    setStatus(`Live data updated for today at ${replayClock.value} ${hostTimeZoneLabel()}.`, false);
    return;
  }

  const { period } = getFormValues();
  const tickers = getSelectedTickers();
  const replaySecond = Number(replayTime.value || 57540);
  const now = Date.now();
  if (
    !force &&
    lastReplayFetchSecond !== null &&
    Math.abs(replaySecond - lastReplayFetchSecond) < REPLAY_FETCH_STEP_SECONDS
  ) {
    fields.contractSummary.textContent = `Clock updated to ${replayClock.value} ${hostTimeZoneLabel()}. Values refresh on the next available one-minute bar.`;
    return;
  }
  if (!force && now - lastReplayFetchStartedAt < REPLAY_MIN_FETCH_INTERVAL_MS) {
    return;
  }

  if (isReplayLoading && replayAbortController) {
    replayAbortController.abort();
  }
  const requestId = ++replayRequestId;
  const controller = new AbortController();
  isReplayLoading = true;
  replayAbortController = controller;
  isInspectingContract = true;
  lastReplayFetchStartedAt = now;

  fields.contractSummary.textContent = "Loading historical replay from SQLite...";
  fields.contractSummary.classList.remove("error");
  fields.contractList.classList.add("is-refreshing");
  if (!renderedContractContentExists()) {
    fields.contractList.textContent = "Loading historical contract candidates...";
  }

  try {
    const { payloads, errors } = await loadOptionReplaysForTickers(tickers, period, {
      signal: controller.signal,
    });
    if (requestId !== replayRequestId) {
      return;
    }
    if (payloads.length === 0) {
      throw new Error(replayErrorMessage(errors));
    }
    lastReplayFetchSecond = replaySecond;
    const renderedHistory = renderOptionReplays(payloads, errors, { refreshHistory });
    if (!renderedHistory && refreshHistory) {
      renderTradeHistory();
    }
  } catch (error) {
    if (requestId === replayRequestId) {
      showReplayError(error);
      renderTradeHistory();
    }
  } finally {
    if (requestId === replayRequestId) {
      isReplayLoading = false;
      replayAbortController = null;
      fields.contractList.classList.remove("is-refreshing");
    }
  }
}

function clearReplayScrubTimer() {
  if (replayScrubTimer !== null) {
    clearTimeout(replayScrubTimer);
    replayScrubTimer = null;
  }
}

function scheduleReplayScrubRefresh() {
  clearReplayScrubTimer();
  if (selectedReplayUsesLiveData()) {
    return;
  }
  fields.contractSummary.classList.remove("error");
  fields.contractSummary.textContent = `Loading ${replayDate.value} at ${replayClock.value} ${hostTimeZoneLabel()}...`;
  replayScrubTimer = setTimeout(async () => {
    replayScrubTimer = null;
    stopLiveMode();
    renderTradeHistory();
    await loadOptionReplay({ force: true });
  }, 300);
}

async function runDaySimulation() {
  const simulationDate = replayDate.value;
  if (!simulationDate || simulationDate >= currentHostDate() || isWeekendDate(simulationDate)) {
    setDaySimulationStatus("Choose a completed weekday before today.", true);
    return;
  }

  daySimulationRunning = true;
  daySimulationStopRequested = false;
  runDaySimulationButton.disabled = false;
  runDaySimulationButton.textContent = "Stop Simulation";
  stopLiveMode();
  stopReplay();
  if (refreshTimer !== null) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (replayAbortController) {
    replayAbortController.abort();
  }

  const { period } = getFormValues();
  const tickers = getSelectedTickers();
  const start = Number(replayTime.min) + DAY_SIMULATION_STEP_SECONDS;
  const end = Number(replayTime.max) - 60;
  const checkpoints = [];
  for (let second = start; second <= end; second += DAY_SIMULATION_STEP_SECONDS) {
    checkpoints.push(second);
  }

  try {
    const cacheRows = await refreshCacheStatus();
    const simulationTickers = tickers.filter((ticker) =>
      cacheRows.some((row) => row.ticker === ticker && row.status === "complete")
    );
    if (simulationTickers.length === 0) {
      throw new Error("No selected ticker is fully cached for this day. Press Cache Day first.");
    }

    for (let index = 0; index < checkpoints.length; index += 1) {
      if (daySimulationStopRequested) {
        break;
      }
      const second = checkpoints[index];
      replayTime.value = String(second);
      updateReplayClock();
      setDaySimulationStatus(
        `Replaying ${simulationTickers.join(", ")} at ${replayClock.value} ${hostTimeZoneLabel()} (${index + 1} of ${checkpoints.length})...`,
        false
      );
      const { payloads, errors } = await loadOptionReplaysForTickers(simulationTickers, period);
      if (payloads.length === 0) {
        throw new Error(replayErrorMessage(errors));
      }
      renderOptionReplays(payloads, errors);
      await refreshReplayLedgerPrices(simulationDate, getReplayMarketClock(), second);
      await simulationDelay(250);
    }

    renderTradeHistory();
    renderPaperLedger();
    setDaySimulationStatus(
      daySimulationStopRequested
        ? "Day simulation stopped. Saved results up to the last completed checkpoint."
        : `Day simulation complete for ${formatContractDate(simulationDate)}.`,
      false
    );
  } catch (error) {
    setDaySimulationStatus(error.message, true);
  } finally {
    daySimulationRunning = false;
    daySimulationStopRequested = false;
    runDaySimulationButton.disabled = false;
    runDaySimulationButton.textContent = "Run Day Simulation";
    scheduleRefresh();
  }
}

async function refreshReplayLedgerPrices(simulationDate, easternClock, localSecond) {
  const openSymbols = [...new Set(
    loadPaperLedger()
      .filter((trade) => trade.status !== "closed" && paperLedgerDay(trade) === simulationDate)
      .map((trade) => trade.symbol)
      .filter(Boolean)
  )];
  if (openSymbols.length === 0) {
    return;
  }
  const query = new URLSearchParams({
    symbols: openSymbols.join(","),
    date: simulationDate,
    time: easternClock,
  });
  const payload = await getJson(`/api/options/prices?${query.toString()}`);
  updatePaperLedgerPrices(payload.prices || {}, `${simulationDate}T${formatClock(localSecond)}`);
}

function simulationDelay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function setDaySimulationStatus(message, isError) {
  if (!daySimulationStatus) {
    return;
  }
  daySimulationStatus.textContent = message;
  daySimulationStatus.classList.remove("hidden");
  daySimulationStatus.classList.toggle("error", Boolean(isError));
}

async function refreshCacheStatus() {
  if (!cacheStatus || !replayDate.value || selectedReplayUsesLiveData()) {
    cachedTickersForReplay = new Set();
    if (cacheStatus) cacheStatus.textContent = "Live sessions use provider data; completed days can be cached after close.";
    return [];
  }
  const { period } = getFormValues();
  try {
    const query = new URLSearchParams({ date: replayDate.value, period });
    const payload = await getJson(`/api/cache/status?${query.toString()}`);
    const rows = Array.isArray(payload.caches) ? payload.caches : [];
    cachedTickersForReplay = new Set(
      rows.filter((row) => row.status === "complete").map((row) => String(row.ticker).toUpperCase())
    );
    if (rows.length === 0) {
      cacheStatus.textContent = "Not cached. Slider playback stays local and will not call an API. Use Cache Day once.";
      cacheStatus.classList.remove("error");
      return rows;
    }
    cacheStatus.textContent = rows.map((row) =>
      `${row.ticker}: ${row.status === "complete" ? `${row.option_contract_count} contracts cached` : row.status}`
    ).join(" · ");
    cacheStatus.classList.toggle("error", rows.some((row) => row.status === "error"));
    return rows;
  } catch (error) {
    cacheStatus.textContent = error.message;
    cacheStatus.classList.add("error");
    return [];
  }
}

async function cacheSelectedDay() {
  const day = replayDate.value;
  if (!day || day > currentHostDate() || isWeekendDate(day)) {
    cacheStatus.textContent = "Choose today after 4:00 PM ET or an earlier completed market day.";
    cacheStatus.classList.add("error");
    return;
  }
  const { period } = getFormValues();
  cacheDayButton.disabled = true;
  cacheStatus.classList.remove("error");
  cacheStatus.textContent = `Caching every recorded contract, stock bar, and GEX row for ${formatContractDate(day)}...`;
  try {
    const payload = await postJson("/api/cache/day", { date: day, period });
    const failed = (payload.results || []).filter((row) => row.status !== "complete");
    cacheStatus.textContent = (payload.results || []).map((row) =>
      `${row.ticker}: ${row.status === "complete" ? `${row.contracts} contracts ready` : row.error}`
    ).join(" · ");
    cacheStatus.classList.toggle("error", failed.length > 0);
    replayOutcomeCache.clear();
    await refreshCacheStatus();
    await loadOptionReplay({ force: true });
    renderTradeHistory();
  } catch (error) {
    cacheStatus.textContent = error.message;
    cacheStatus.classList.add("error");
  } finally {
    cacheDayButton.disabled = false;
  }
}

function renderOptionReplay(payload) {
  renderOptionReplays([payload], []);
}

function renderOptionReplays(payloads, errors = [], { refreshHistory = true } = {}) {
  return withViewportAnchor(() => {
    const primary = payloads[0];
    if (primary?.analysis) {
      lastAnalysis = primary.analysis;
      renderAnalysis(primary.analysis);
    }
    rememberTickerAnalyses(payloads.map((payload) => ({
      ticker: payload.analysis?.ticker || payload.recommendation?.ticker,
      payload: payload.analysis || payload,
    })));
    renderMultiTickerSummary(payloads.map((payload) => ({
      ticker: payload.analysis?.ticker || payload.recommendation?.ticker || "Unknown",
      payload: payload.analysis,
    })).concat(errors.map((error) => ({ ticker: error.ticker, error: error.message }))));
    setStatus(`Replay maps updated for ${payloads.length} ticker${payloads.length === 1 ? "" : "s"} at ${replayClock.value} ${hostTimeZoneLabel()}.`, false);

    const summaries = payloads.map((payload) => {
      const recommendation = payload.recommendation || {};
      const ticker = recommendation.ticker || payload.analysis?.ticker || "Ticker";
      return `${ticker}: ${recommendation.trade_permission || "no read"}`;
    });
    if (errors.length) {
      summaries.push(...errors.map((error) => `${error.ticker}: unavailable`));
    }
    fields.contractSummary.classList.toggle("error", payloads.length === 0);
    fields.contractSummary.textContent = `${primary?.date || replayDate.value} ${replayClock.value} ${hostTimeZoneLabel()} | ${summaries.join(" | ")}`;

    let recorded = false;
    for (const payload of payloads) {
      if (!payload.cached_replay) {
        recorded = recordPayloadTradePermission(payload, "replay", { render: false }) || recorded;
      }
    }
    if (recorded && refreshHistory) {
      renderTradeHistory({ preserveScroll: false });
    }
    const bestPayload = selectBestPayload(payloads, "replay");
    if (bestPayload) {
      renderBestPick(bestPayload, "replay", { record: false });
    } else {
      resetBestPick();
    }

    renderTickerContractColumns(payloads, errors, "replay");
    return recorded;
  });
}

function initializeReplayControls() {
  const today = new Date(`${currentHostDate()}T12:00:00`);
  const priorDay = new Date(today);
  priorDay.setDate(today.getDate() - 1);
  while (priorDay.getDay() === 0 || priorDay.getDay() === 6) {
    priorDay.setDate(priorDay.getDate() - 1);
  }
  replayDate.value = formatDateInput(priorDay);
  applyHostMarketWindow(replayDate.value);
  updateReplayClock();
  for (const button of speedButtons) {
    button.classList.toggle("active", Number(button.dataset.speed) === replaySpeed);
  }
}

function initializeTradeHistoryExportControls() {
  const selectedDate = replayDate.value || currentHostDate();
  if (historyStartDate && !historyStartDate.value) {
    historyStartDate.value = selectedDate;
  }
  if (historyEndDate && !historyEndDate.value) {
    historyEndDate.value = selectedDate;
  }
  updateHistoryRangeCount();
}

function syncHistoryExportDatesToReplayDate() {
  const selectedDate = replayDate.value || currentHostDate();
  if (historyStartDate && historyEndDate && historyStartDate.value === historyEndDate.value) {
    historyStartDate.value = selectedDate;
    historyEndDate.value = selectedDate;
  }
}

function initializeMarketMode() {
  const market = currentHostMarketSnapshot();
  replayDate.value = market.date;
  applyHostMarketWindow(market.date);
  replayTime.value = String(market.clampedSeconds);
  updateReplayClock();
  updateTickerSelectionCount();
  recordTrackedTickers(market.date, getSelectedTickers());
  renderTrackingOverview();

  if (market.isOpen) {
    isInspectingContract = false;
    startLiveMode();
    setStatus(`Market is open. Auto Live started at ${replayClock.value} ${hostTimeZoneLabel()}.`, false);
    return;
  }

  stopLiveMode();
  syncHistoryExportDatesToReplayDate();
  fields.contractSummary.textContent = "Market is closed. Historical replay mode is ready.";
  setStatus("Market is closed. Today's trade history is still selected; use historical replay controls to analyze another session.", false);
  loadOptionReplay({ force: true });
}

function isWeekendDate(value) {
  const date = new Date(`${value}T12:00:00`);
  return date.getDay() === 0 || date.getDay() === 6;
}

function currentHostMarketSnapshot() {
  const now = new Date();
  const date = formatDateInput(now);
  const window = hostMarketWindow(date);
  const seconds = localSeconds(now);
  return {
    date,
    seconds,
    clampedSeconds: Math.min(Math.max(seconds, window.min), window.max),
    isOpen: now >= window.open && now <= window.close,
  };
}

function currentHostDate() {
  return formatDateInput(new Date());
}

function selectedReplayUsesLiveData() {
  return replayDate.value === currentHostDate() && currentHostMarketSnapshot().isOpen;
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function updateReplayClock() {
  const seconds = Number(replayTime.value || 46740);
  replayClock.value = formatClock(seconds);
  if (replayTimezone) {
    replayTimezone.textContent = hostTimeZoneLabel();
  }
}

function getReplayMarketClock() {
  return getReplayPoint().marketClock;
}

function getReplayPoint() {
  const [year, month, day] = replayDate.value.split("-").map(Number);
  const seconds = Number(replayTime.value || 46740);
  const localDateTime = new Date(
    year,
    month - 1,
    day,
    Math.floor(seconds / 3600),
    Math.floor((seconds % 3600) / 60),
    seconds % 60
  );
  const parts = timeZoneParts(localDateTime, MARKET_TIME_ZONE);
  return {
    iso: localDateTime.toISOString(),
    marketClock: `${parts.hour}:${parts.minute}:${parts.second}`,
  };
}

async function jumpToTodayNow() {
  const market = currentHostMarketSnapshot();
  const marketDate = market.date;

  replayDate.value = marketDate;
  applyHostMarketWindow(marketDate);
  replayTime.value = String(market.clampedSeconds);
  lastReplayFetchSecond = null;
  updateReplayClock();
  renderTrackingOverview();
  renderTradeHistory();

  if (market.isOpen) {
    isInspectingContract = false;
    await runAnalysis();
    setStatus(`Live view updated to today at ${replayClock.value} ${hostTimeZoneLabel()}.`, false);
    return;
  }

  setStatus(`Market is outside regular hours. Showing the nearest session point for ${marketDate} at ${replayClock.value} ${hostTimeZoneLabel()}.`, false);
  await loadOptionReplay({ force: true });
}

function timeZoneParts(date, timeZone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type) => parts.find((item) => item.type === type)?.value || "00";
  return {
    year: part("year"),
    month: part("month"),
    day: part("day"),
    hour: part("hour"),
    minute: part("minute"),
    second: part("second"),
  };
}

function zonedDateTimeToInstant(dateValue, clock, timeZone) {
  const [year, month, day] = dateValue.split("-").map(Number);
  const [hour, minute, second] = clock.split(":").map(Number);
  const nominal = Date.UTC(year, month - 1, day, hour, minute, second || 0);
  let instant = nominal;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const parts = timeZoneParts(new Date(instant), timeZone);
    const represented = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour), Number(parts.minute), Number(parts.second)
    );
    instant += nominal - represented;
  }
  return new Date(instant);
}

function localSeconds(date) {
  return date.getHours() * 3600 + date.getMinutes() * 60 + date.getSeconds();
}

function hostMarketWindow(dateValue) {
  const open = zonedDateTimeToInstant(dateValue, "09:30:00", MARKET_TIME_ZONE);
  const close = zonedDateTimeToInstant(dateValue, "16:00:00", MARKET_TIME_ZONE);
  return { open, close, min: localSeconds(open), max: localSeconds(close) };
}

function applyHostMarketWindow(dateValue) {
  if (!dateValue) {
    return;
  }
  const window = hostMarketWindow(dateValue);
  replayTime.min = String(window.min);
  replayTime.max = String(window.max);
  const value = Number(replayTime.value);
  replayTime.value = String(Math.min(Math.max(value, window.min), window.max));
}

function hostTimeZoneLabel() {
  return new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(new Date())
    .find((part) => part.type === "timeZoneName")?.value || "Local";
}

function toggleReplay() {
  if (replayTimer !== null) {
    stopReplay();
    return;
  }

  stopLiveMode();
  isInspectingContract = true;
  replayClockRemainder = 0;
  replayTimer = setTimeout(runReplayClockTick, REPLAY_CLOCK_TICK_MS);
  updatePlaybackButton();
}

function runReplayClockTick() {
  if (replayTimer === null) {
    return;
  }

  replayClockRemainder += replaySpeed * (REPLAY_CLOCK_TICK_MS / 1000);
  const wholeSeconds = Math.floor(replayClockRemainder);
  replayClockRemainder -= wholeSeconds;

  if (wholeSeconds > 0) {
    const previousValue = Number(replayTime.value);
    const nextValue = Math.min(previousValue + wholeSeconds, Number(replayTime.max));
    replayTime.value = String(nextValue);
    updateReplayClock();
    const crossedMinute = Math.floor(previousValue / REPLAY_FETCH_STEP_SECONDS) !==
      Math.floor(nextValue / REPLAY_FETCH_STEP_SECONDS);
    if (crossedMinute) {
      // Historical outcome rows are SQLite-backed after their first contract
      // load, so update them at every simulated minute independently of the
      // slower GEX/contract replay request.
      renderTradeHistory();
      if (!isReplayLoading) {
        loadOptionReplay({ refreshHistory: false });
      }
    }
    if (nextValue >= Number(replayTime.max)) {
      stopReplay();
      return;
    }
  }

  // Schedule from the end of this tick. If rendering or SQLite work takes a
  // moment, playback pauses briefly instead of applying missed ticks at once.
  replayTimer = setTimeout(runReplayClockTick, REPLAY_CLOCK_TICK_MS);
}

function stopReplay() {
  if (replayTimer !== null) {
    clearTimeout(replayTimer);
    replayTimer = null;
  }
  replayClockRemainder = 0;
  updatePlaybackButton();
}

function updatePlaybackButton() {
  replayPlay.textContent = liveTimer !== null || replayTimer !== null ? "Pause" : "Play";
  replayPlay.classList.toggle("active", liveTimer !== null || replayTimer !== null);
}

function formatClock(totalSeconds) {
  const hour = Math.floor(totalSeconds / 3600);
  const minute = Math.floor((totalSeconds % 3600) / 60);
  const second = totalSeconds % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`;
}

function parseClock(value) {
  const match = String(value || "").match(/^(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) {
    return null;
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  const second = Number(match[3] || 0);
  if (hour > 23 || minute > 59 || second > 59) {
    return null;
  }
  return hour * 3600 + minute * 60 + second;
}

function renderOptionRecommendation(payload) {
  renderOptionRecommendations([payload], []);
}

function renderOptionRecommendations(payloads, errors = []) {
  return withViewportAnchor(() => {
    const primary = payloads[0];
    if (primary?.analysis) {
      lastAnalysis = primary.analysis;
      renderAnalysis(primary.analysis);
    }
    rememberTickerAnalyses(payloads.map((payload) => ({
      ticker: payload.analysis?.ticker || payload.ticker,
      payload: payload.analysis || payload,
    })));
    renderMultiTickerSummary(payloads.map((payload) => ({
      ticker: payload.analysis?.ticker || payload.ticker || "Unknown",
      payload: payload.analysis || payload,
    })).concat(errors.map((error) => ({ ticker: error.ticker, error: error.message }))));

    const summaries = payloads.map((payload) => {
      const ticker = payload.ticker || payload.analysis?.ticker || "Ticker";
      return `${ticker}: ${payload.trade_permission || "no read"}`;
    });
    if (errors.length) {
      summaries.push(...errors.map((error) => `${error.ticker}: unavailable`));
    }
    fields.contractSummary.classList.toggle("error", payloads.length === 0);
    fields.contractSummary.textContent = summaries.join(" | ");

    let recorded = false;
    for (const payload of payloads) {
      recorded = recordPayloadTradePermission(payload, "live", { render: false }) || recorded;
    }
    if (recorded) {
      renderTradeHistory({ preserveScroll: false });
    }
    const bestPayload = selectBestPayload(payloads, "live");
    if (bestPayload) {
      renderBestPick(bestPayload, "live", { record: false });
    } else {
      resetBestPick();
    }

    renderTickerContractColumns(payloads, errors, "live");
  });
}

function payloadRecommendation(payload, mode) {
  return mode === "replay" ? payload.recommendation || {} : payload;
}

function payloadWarning(payload, mode) {
  if (mode === "replay") {
    return payload.warning || "";
  }
  return Array.isArray(payload.warnings) ? payload.warnings.join(" ") : payload.warning || "";
}

function renderTickerContractColumns(payloads, errors, mode) {
  fields.contractList.innerHTML = "";
  fields.contractList.classList.toggle("multi-ticker-columns", payloads.length + errors.length > 1);
  for (const payload of payloads) {
    const recommendation = payloadRecommendation(payload, mode);
    const analysis = payload.analysis || {};
    const ticker = recommendation.ticker || analysis.ticker || payload.ticker || "Ticker";
    const candidates = (payload.candidates || []).slice(0, 3);
    const column = document.createElement("section");
    column.className = `ticker-contract-column permission-${permissionClass(recommendation.trade_permission)}`;
    column.dataset.ticker = ticker;
    column.dataset.scrollKey = `contract-column:${ticker}`;
    column.innerHTML = `
      <header class="ticker-column-header">
        <div>
          <strong>${escapeHtml(ticker)}</strong>
          <span>${escapeHtml(recommendation.trade_permission || "No trade read")}</span>
        </div>
        <div class="ticker-column-stats">
          <span>${escapeHtml(recommendation.bias || analysis.bias || "unknown")}</span>
          <span>Spot ${formatOptionalNumber(analysis.spot ?? recommendation.gex_spot)}</span>
        </div>
      </header>
      <div class="ticker-candidate-list"></div>
    `;
    const list = column.querySelector(".ticker-candidate-list");
    if (candidates.length === 0) {
      const empty = document.createElement("p");
      empty.className = "ticker-column-empty";
      empty.textContent = payloadWarning(payload, mode)
        || recommendation.recommendation
        || "No ranked contracts are available for this ticker.";
      list.appendChild(empty);
    } else {
      candidates.forEach((candidate, index) => list.appendChild(createTickerCandidateRow(candidate, mode, index + 1)));
    }
    fields.contractList.appendChild(column);
  }

  for (const error of errors) {
    const column = document.createElement("section");
    column.className = "ticker-contract-column error";
    column.dataset.ticker = error.ticker;
    column.dataset.scrollKey = `contract-column:${error.ticker}`;
    column.innerHTML = `
      <header class="ticker-column-header">
        <div><strong>${escapeHtml(error.ticker)}</strong><span>Unavailable</span></div>
      </header>
      <p class="ticker-column-empty">${escapeHtml(error.message)}</p>
    `;
    fields.contractList.appendChild(column);
  }

  if (payloads.length === 0 && errors.length === 0) {
    fields.contractList.textContent = mode === "replay" ? "No replay contracts found." : "No contract candidates.";
  }
}

function createTickerCandidateRow(candidate, mode, rank) {
  const replay = mode === "replay";
  const price = replay ? candidate.close : candidate.mid;
  const row = document.createElement("button");
  row.type = "button";
  row.className = `contract-row contract-${contractSide(candidate)}`;
  row.innerHTML = `
    <span class="candidate-rank">Pick #${rank}</span>
    ${contractTitleMarkup(candidate)}
    ${optionSparklineMarkup(candidate)}
    ${replay
      ? contractMetric("Price / cost", formatOptionPriceAndCost(price), "The old quoted option price and total cost for one 100-share contract at the selected replay time.")
      : contractMetric("Mid / cost", formatOptionPriceAndCost(price), "The quote midpoint and approximate total debit for one 100-share contract.")}
    ${replay
      ? contractMetric("Day", formatPercent(candidate.day_change_pct), "How much this option had moved that day by the selected replay time.")
      : contractMetric("Spread", formatPercent(candidate.spread_pct), "The gap between buy and sell prices. Smaller is usually better.")}
    ${replay
      ? contractMetric("Volume", formatNumber(candidate.volume || 0), "How many of this exact option traded in the latest one-minute bar.")
      : contractMetric("Open int", candidate.open_interest ?? "n/a", "How many of this option are still open in the market.")}
    ${replay
      ? contractMetric("Replay score", formatNumber(candidate.replay_score), "The bot's historical replay rank for this contract.")
      : contractMetric("Score", formatNumber(candidate.score), "The bot's quality rank for this contract.")}
    <small>${greekSummary(candidate)}</small>
  `;
  row.addEventListener("click", () => {
    isInspectingContract = true;
    stageCandidate(
      candidate,
      price,
      replay
        ? `Staged ${candidate.symbol} from replay at ${replayClock.value} ${hostTimeZoneLabel()}.`
        : `Staged ${candidate.symbol} as a paper limit order.`
    );
  });
  return row;
}

function payloadHasTradePermission(payload, mode) {
  const recommendation = payloadRecommendation(payload, mode);
  return String(recommendation.trade_permission || "").toLowerCase().includes("possible trade") && !payloadWarning(payload, mode);
}

function selectBestPayload(payloads, mode) {
  const withCandidates = payloads.filter((payload) => (payload.candidates || []).length > 0);
  const eligible = withCandidates.filter((payload) => payloadHasTradePermission(payload, mode));
  const pool = eligible.length > 0 ? eligible : withCandidates;
  return [...pool].sort((left, right) => {
    const leftCandidate = left.candidates[0] || {};
    const rightCandidate = right.candidates[0] || {};
    const leftScore = Number(mode === "replay" ? leftCandidate.replay_score : leftCandidate.score) || 0;
    const rightScore = Number(mode === "replay" ? rightCandidate.replay_score : rightCandidate.score) || 0;
    return rightScore - leftScore;
  })[0] || null;
}

function recordPayloadTradePermission(payload, mode, { render = true } = {}) {
  if (!payloadHasTradePermission(payload, mode)) {
    return false;
  }
  const recommendation = payloadRecommendation(payload, mode);
  recordTradePermissionPicks({
    candidates: payload.candidates || [],
    recommendation,
    payload,
    mode,
    priceLabel: mode === "replay" ? "last replay close" : "mid",
    render,
  });
  return true;
}

function renderBestPick(payload, mode, { record = true } = {}) {
  const recommendation = payloadRecommendation(payload, mode);
  const candidate = (payload.candidates || [])[0];

  if (!candidate) {
    currentBestPick = null;
    fields.bestPick.classList.remove("hidden");
    fields.bestPick.classList.add("best-pick-wait");
    fields.bestPickAction.textContent = "No contract pick";
    fields.bestPickContract.textContent = "No ranked candidate is available for this read.";
    fields.bestPickReason.textContent = payload.warning || "Run a scan after GEX and Alpaca both return usable data.";
    fields.bestPickExit.textContent = "No sell plan until there is an entry candidate.";
    if (stageBestPickButton) {
      stageBestPickButton.disabled = true;
    }
    return;
  }

  const permission = String(recommendation.trade_permission || "").toLowerCase();
  const bias = String(recommendation.bias || "unknown");
  const score = mode === "replay" ? candidate.replay_score : candidate.score;
  const entryPrice = mode === "replay" ? candidate.close : candidate.mid;
  const priceLabel = mode === "replay" ? "last replay close" : "mid";
  const hasTradePermission = permission.includes("possible trade");
  const warning = payloadWarning(payload, mode);
  const isStandDown = !hasTradePermission || Boolean(warning);
  const action = hasTradePermission && !warning ? "Buy candidate after confirmation" : "Wait / watch only";
  const reasonParts = [
    `GEX is ${bias}${permission ? ` with ${permission} permission` : ""}.`,
    `${candidate.symbol} is the top ranked ${candidate.contract_type} with score ${formatNumber(score)}.`,
  ];

  if (entryPrice) {
    reasonParts.push(`Reference ${priceLabel}: ${formatCurrency(entryPrice)}.`);
  }
  if (warning) {
    reasonParts.push(warning);
  }

  currentBestPick = {
    candidate,
    entryPrice,
    message:
      mode === "replay"
        ? `Staged ${candidate.symbol} from the best replay pick.`
        : `Staged ${candidate.symbol} from the best watchlist pick.`,
  };

  fields.bestPick.classList.remove("hidden", "best-pick-wait");
  fields.bestPick.classList.toggle("best-pick-wait", isStandDown);
  fields.bestPickAction.textContent = action;
  fields.bestPickContract.textContent = `${readableContractName(candidate)} | ${priceLabel} ${formatOptionPriceAndCost(entryPrice)}`;
  fields.bestPickReason.textContent = reasonParts.join(" ");
  fields.bestPickExit.textContent = sellPlanText(entryPrice);
  if (stageBestPickButton) {
    stageBestPickButton.disabled = false;
  }

  if (record && !isStandDown) {
    recordTradePermissionPicks({
      candidates: payload.candidates || [],
      recommendation,
      payload,
      mode,
      priceLabel,
    });
  }
}

function resetBestPick() {
  currentBestPick = null;
  fields.bestPick.classList.add("hidden");
  fields.bestPick.classList.remove("best-pick-wait");
  fields.bestPickAction.textContent = "-";
  fields.bestPickContract.textContent = "-";
  fields.bestPickReason.textContent = "-";
  fields.bestPickExit.textContent = "-";
  if (stageBestPickButton) {
    stageBestPickButton.disabled = true;
  }
}

function stageCandidate(candidate, entryPrice, message) {
  if (!paperOrderForm) {
    fields.contractSummary.textContent = message;
    return;
  }
  paperOrderForm.elements.symbol.value = candidate.symbol;
  paperOrderForm.elements.side.value = "buy";
  paperOrderForm.elements.qty.value = "1";
  paperOrderForm.elements.type.value = "limit";
  paperOrderForm.elements.limit_price.value = entryPrice ? Number(entryPrice).toFixed(2) : "";
  setAlpacaStatus(message, false);
}

function recordTradePermissionPicks({ candidates, recommendation, payload, mode, priceLabel, render = true }) {
  const timestamp = pickTimestamp({ recommendation, payload, mode });
  const items = (candidates || [])
    .slice(0, MAX_RECORDED_PERMISSION_CANDIDATES)
    .map((candidate, index) =>
      buildTradePermissionItem({
        candidate,
        recommendation,
        payload,
        mode,
        priceLabel,
        timestamp,
        rank: index + 1,
      })
    )
    .filter(Boolean);

  if (items.length === 0) {
    return;
  }

  const history = loadTradeHistory();
  const incomingIds = new Set(items.map((item) => item.id));
  const withoutDuplicates = history.filter((existing) => !incomingIds.has(existing.id));
  saveTradeHistory([...items, ...withoutDuplicates].slice(0, MAX_TRADE_HISTORY_ITEMS));
  recordPaperLedgerTrade(items[0]);
  renderTrackingOverview();
  if (render) {
    renderTradeHistory();
  }
}

function buildTradePermissionItem({ candidate, recommendation, payload, mode, priceLabel, timestamp, rank }) {
  if (!candidate.symbol) {
    return null;
  }

  const entryPrice = mode === "replay" ? candidate.close : candidate.mid;
  const score = mode === "replay" ? candidate.replay_score : candidate.score;
  const analysis = payload.analysis || recommendation.analysis || lastAnalysis || {};
  const technicals = analysis.technicals || {};
  const baseCandidate = (recommendation.candidates || payload.candidates || [])
    .find((item) => item.symbol === candidate.symbol) || candidate;
  const decisionSnapshot = {
    timestamp: timestamp.iso,
    gex: {
      bias: analysis.bias || recommendation.bias || "unknown",
      score: analysis.score ?? null,
      permission: analysis.trade_permission || recommendation.trade_permission || "unknown",
      spot: analysis.spot ?? recommendation.gex_spot ?? null,
      zeroGamma: analysis.zero_gamma ?? null,
    },
    technicals: {
      lastPrice: technicals.last_price ?? null,
      vwap: technicals.vwap ?? null,
      sma50: technicals.sma_50 ?? null,
      sma200: technicals.sma_200 ?? null,
      scoreAdjustment: technicals.score_adjustment ?? null,
      reasons: Array.isArray(technicals.reasons) ? technicals.reasons : [],
    },
    contract: {
      symbol: candidate.symbol,
      type: candidate.contract_type || contractSide(candidate),
      expiration: candidate.expiration_date ?? baseCandidate.expiration_date ?? null,
      strike: candidate.strike_price ?? baseCandidate.strike_price ?? null,
      entry: entryPrice ?? null,
      bid: baseCandidate.bid ?? null,
      ask: baseCandidate.ask ?? null,
      mid: baseCandidate.mid ?? candidate.close ?? null,
      spreadPercent: baseCandidate.spread_pct ?? null,
      openInterest: baseCandidate.open_interest ?? null,
      volume: candidate.volume ?? baseCandidate.volume ?? null,
      delta: candidate.delta ?? baseCandidate.delta ?? null,
      gamma: candidate.gamma ?? baseCandidate.gamma ?? null,
      impliedVolatility: candidate.implied_volatility ?? baseCandidate.implied_volatility ?? null,
      rankingScore: score ?? null,
    },
  };
  return {
    id: `${mode}:${timestamp.iso}:${rank}:${candidate.symbol}`,
    timestamp,
    replayDate: mode === "replay" && payload.date ? payload.date : timestamp.day,
    mode,
    rank,
    ticker: recommendation.ticker || contractUnderlying(candidate),
    underlying: candidate.underlying_symbol || recommendation.underlying_symbol || contractUnderlying(candidate),
    bias: recommendation.bias || "unknown",
    permission: recommendation.trade_permission || "trade permission",
    contract: readableContractName(candidate),
    symbol: candidate.symbol,
    side: contractSide(candidate),
    expirationDate: candidate.expiration_date,
    strikePrice: candidate.strike_price,
    contractType: candidate.contract_type || contractSide(candidate),
    entryPrice,
    entrySpot: recommendation.gex_spot || null,
    pricePath: Array.isArray(candidate.price_path) ? candidate.price_path : [],
    entryGreeks: {
      delta: candidate.delta ?? null,
      gamma: candidate.gamma ?? null,
      implied_volatility: candidate.implied_volatility ?? null,
      estimated: Boolean(candidate.greeks_estimated),
    },
    priceLabel,
    score,
    sellPlan: sellPlanText(entryPrice),
    decisionSnapshot,
  };
}

function pickTimestamp({ recommendation, payload, mode }) {
  if (mode === "replay" && payload.date && payload.selected_time) {
    return {
      iso: `${payload.date}T${payload.selected_time}`,
      day: payload.date,
      label: `${formatContractDate(payload.date)} ${formatDisplayTime(payload.selected_time)}`,
    };
  }
  if (recommendation.gex_timestamp) {
    const date = new Date(Number(recommendation.gex_timestamp) * 1000);
    return {
      iso: date.toISOString(),
      day: date.toISOString().slice(0, 10),
      label: formatHistoryDate(date),
    };
  }
  const now = new Date();
  return {
    iso: now.toISOString(),
    day: now.toISOString().slice(0, 10),
    label: formatHistoryDate(now),
  };
}

function renderTradeHistory({ preserveScroll = true, refreshData = true } = {}) {
  if (preserveScroll) {
    return withViewportAnchor(() => renderTradeHistory({ preserveScroll: false, refreshData }));
  }
  const selectedDate = replayDate.value;
  const selectedTickers = getSelectedTickers();
  const isHistoricalDay = Boolean(selectedDate && selectedDate !== currentHostDate());
  const replayPoint = isHistoricalDay ? getReplayPoint() : null;
  if (isHistoricalDay) {
    ensureHistoricalDateLoaded(selectedDate);
  }
  const sourceHistory = isHistoricalDay
    ? historicalTradeHistoryForDate(selectedDate)
    : loadTradeHistory();
  const history = sourceHistory.filter((item) =>
    historyItemDate(item) === selectedDate &&
    (isHistoricalDay || matchesTickerFilter(item, selectedTickers)) &&
    historyItemVisibleAtReplayPoint(item, selectedDate, replayPoint)
  );
  renderLowerConfidenceLog(history);
  renderPaperLedger({ preserveScroll: false });
  if (history.length === 0) {
    if (isHistoricalDay && persistentHistoryRequests.has(selectedDate) && !persistentHistoryByDate.has(selectedDate)) {
      fields.tradeHistory.textContent = `Loading saved history for ${formatContractDate(selectedDate)}...`;
      return;
    }
    fields.tradeHistory.textContent = selectedDate
      ? `No trade-permission picks recorded by ${replayClock.value} ${hostTimeZoneLabel()} on ${formatContractDate(selectedDate)}.`
      : "No trade-permission picks yet.";
    return;
  }
  fields.tradeHistory.innerHTML = "";
  if (isHistoricalDay) {
    renderHistoricalTickerGroups(history, selectedDate, refreshData, replayPoint);
  } else {
    for (const item of history) {
      fields.tradeHistory.appendChild(createTradeHistoryRow(item));
    }
    refreshRenderedTradeHistory(history, { refreshData });
  }
}

function renderLowerConfidenceLog(history) {
  if (!fields.lowerConfidenceLog) {
    return;
  }
  const skipped = history
    .filter((item) => {
      const score = optionalNumber(item.score);
      return score !== null && score < PAPER_LEDGER_MIN_SCORE;
    })
    .slice(0, 100);
  if (skipped.length === 0) {
    fields.lowerConfidenceLog.textContent = `No permission signals below score ${PAPER_LEDGER_MIN_SCORE} at this replay point.`;
    return;
  }
  fields.lowerConfidenceLog.innerHTML = "";
  for (const item of skipped) {
    const row = document.createElement("div");
    row.className = `lower-confidence-row contract-${item.side || "call"}`;
    row.innerHTML = `
      <span><strong>${escapeHtml(item.timestamp?.label || "-")}</strong><em>${escapeHtml(item.contract || item.symbol || "Unknown contract")}</em></span>
      <span>${escapeHtml(historyItemTicker(item))}</span>
      <span>${escapeHtml(item.bias || "-")}</span>
      <span>Score ${formatOptionalNumber(item.score)}</span>
      <span>Skipped by ledger</span>
    `;
    fields.lowerConfidenceLog.appendChild(row);
  }
}

function historicalTradeHistoryForDate(day) {
  const browserRows = loadTradeHistory().filter((item) => historyItemDate(item) === day);
  const databaseRows = persistentHistoryByDate.get(day)?.tradeHistory || [];
  return mergePersistentRecords(databaseRows, browserRows, tradeHistoryMergeKey)
    .sort((a, b) => String(b.timestamp?.iso || "").localeCompare(String(a.timestamp?.iso || "")));
}

function historicalPaperLedgerForDate(day) {
  const browserRows = loadPaperLedger().filter((trade) => paperLedgerDay(trade) === day);
  const databaseRows = persistentHistoryByDate.get(day)?.paperLedger || [];
  return uniquePaperLedgerTrades(mergePersistentRecords(databaseRows, browserRows, paperLedgerMergeKey));
}

function ensureHistoricalDateLoaded(day) {
  if (!day || day === currentHostDate() || persistentHistoryByDate.has(day)) {
    return Promise.resolve(persistentHistoryByDate.get(day) || null);
  }
  if (persistentHistoryRequests.has(day)) {
    return persistentHistoryRequests.get(day);
  }
  const request = getJson(`/api/storage/history?date=${encodeURIComponent(day)}`)
    .then((payload) => {
      persistentHistoryByDate.set(day, {
        tradeHistory: Array.isArray(payload.trade_history) ? payload.trade_history : [],
        paperLedger: Array.isArray(payload.paper_ledger) ? payload.paper_ledger : [],
        trackedTickers: Array.isArray(payload.tracked_tickers) ? payload.tracked_tickers : [],
      });
      renderTradeHistory();
      renderPaperLedger();
      return payload;
    })
    .catch((error) => {
      console.warn(`Could not load SQLite history for ${day}.`, error);
      persistentHistoryByDate.set(day, {
        tradeHistory: [],
        paperLedger: [],
        trackedTickers: [],
        loadError: String(error?.message || error),
      });
      renderTradeHistory();
      return null;
    })
    .finally(() => {
      persistentHistoryRequests.delete(day);
    });
  persistentHistoryRequests.set(day, request);
  return request;
}

function renderHistoricalTickerGroups(history, selectedDate, refreshData, replayPoint) {
  const grouped = new Map();
  for (const item of history) {
    const ticker = historyItemTicker(item);
    if (!grouped.has(ticker)) {
      grouped.set(ticker, []);
    }
    grouped.get(ticker).push(item);
  }
  if (historyGroupDate !== selectedDate) {
    historyGroupDate = selectedDate;
    openHistoryTickerGroups.clear();
    const firstTicker = [...grouped.keys()].sort()[0];
    if (firstTicker) {
      openHistoryTickerGroups.add(firstTicker);
    }
  }

  for (const ticker of [...grouped.keys()].sort()) {
    const items = grouped.get(ticker);
    const group = document.createElement("details");
    group.className = "history-ticker-group";
    group.dataset.ticker = ticker;
    group.open = openHistoryTickerGroups.has(ticker);

    const summary = document.createElement("summary");
    summary.innerHTML = historicalTickerSummaryMarkup(ticker, items);
    group.appendChild(summary);

    const rows = document.createElement("div");
    rows.className = "history-ticker-rows";
    for (const item of items) {
      rows.appendChild(createTradeHistoryRow(item));
    }
    group.appendChild(rows);
    group.addEventListener("toggle", () => {
      if (group.open) {
        openHistoryTickerGroups.add(ticker);
        refreshRenderedTradeHistory(items, { refreshData: true, replayPoint });
      } else {
        openHistoryTickerGroups.delete(ticker);
      }
    });
    fields.tradeHistory.appendChild(group);
    if (group.open) {
      refreshRenderedTradeHistory(items, { refreshData, replayPoint });
    }
  }
}

function historicalTickerSummaryMarkup(ticker, items) {
  const uniqueContracts = new Set(items.map((item) => String(item.symbol || "")).filter(Boolean)).size;
  const scores = items.map((item) => optionalNumber(item.score)).filter((value) => value !== null);
  const averageScore = scores.length
    ? scores.reduce((total, value) => total + value, 0) / scores.length
    : null;
  const first = items[items.length - 1]?.timestamp?.label || "-";
  const latest = items[0]?.timestamp?.label || "-";
  return `
    <span class="history-ticker-name">${escapeHtml(ticker)}</span>
    <span class="history-ticker-metric"><strong>${items.length}</strong> signals</span>
    <span class="history-ticker-metric"><strong>${uniqueContracts}</strong> contracts</span>
    <span class="history-ticker-metric">Avg score <strong>${formatOptionalNumber(averageScore)}</strong></span>
    <span class="history-ticker-window">${escapeHtml(first)} to ${escapeHtml(latest)}</span>
  `;
}

function historyItemTicker(item) {
  return String(item.ticker || item.underlying || contractUnderlying(item || {}) || "Unknown").toUpperCase();
}

function createTradeHistoryRow(item) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = `trade-history-row contract-${item.side || "call"}`;
  row.dataset.historyId = item.id || "";
  row.dataset.symbol = item.symbol || "";
  row.dataset.entryPrice = item.entryPrice || "";
  row.dataset.scrollKey = `history:${item.id || item.symbol || item.timestamp?.iso || ""}`;
  row.innerHTML = `
    <span class="history-contract">
      <strong>${item.timestamp?.label || "-"}</strong>
      <em>${historyRankLabel(item)}${item.contract || item.symbol || "Unknown contract"}</em>
    </span>
    <span class="history-tags">
      <span class="history-pill history-bias">${item.bias || "-"}</span>
      <span class="history-pill">Score ${formatOptionalNumber(item.score)}</span>
    </span>
    <span class="history-stat history-recorded-stat"><i>Recorded</i><strong>${formatCurrency(item.entryPrice)}</strong></span>
    <span class="history-stat history-high-stat"><i class="history-high-label">Highest after buy</i><strong class="history-high">Loading...</strong><em class="history-high-time">-</em><em class="history-high-greeks">-</em></span>
    <span class="history-stat history-current-stat"><i>Last traded</i><strong class="history-current">Loading...</strong><em class="history-current-time">-</em></span>
    <span class="history-stat history-change-stat"><i>Change</i><strong class="history-change">-</strong></span>
    <span class="history-stat history-exit-stat"><i>Exit</i><strong class="history-exit">Checking...</strong></span>
  `;
  row.addEventListener("click", () => {
    stageCandidate(
      { symbol: item.symbol },
      item.entryPrice,
      `${item.symbol} selected from trade permission history.`
    );
  });
  return row;
}

function refreshRenderedTradeHistory(history, { refreshData = true, replayPoint = null } = {}) {
  if (daySimulationRunning || !refreshData || history.length === 0) {
    return;
  }
  const historicalReplayPoint = replayDate.value !== currentHostDate()
    ? (replayPoint || getReplayPoint())
    : null;
  const outcomeUpdate = updateTradeHistoryOutcomes(history, {
    replayPoint: historicalReplayPoint,
    persist: !historicalReplayPoint,
  });
  if (!historicalReplayPoint) {
    Promise.allSettled([outcomeUpdate, updateTradeHistoryPrices(history)]);
  }
}

function historyItemVisibleAtReplayPoint(item, selectedDate, replayPoint = null) {
  if (!selectedDate || selectedDate === currentHostDate()) {
    return true;
  }
  const timestampIso = String(item.timestamp?.iso || "");
  if (item.mode === "replay") {
    const recordedMarketClock = timestampIso.match(/T(\d{2}:\d{2}:\d{2})/)?.[1];
    return !recordedMarketClock || recordedMarketClock <= (replayPoint || getReplayPoint()).marketClock;
  }
  const recordedAt = new Date(timestampIso);
  if (!Number.isFinite(recordedAt.getTime())) {
    return true;
  }
  const recordedLocalDate = formatDateInput(recordedAt);
  if (recordedLocalDate !== selectedDate) {
    return recordedLocalDate < selectedDate;
  }
  return localSeconds(recordedAt) <= Number(replayTime.value);
}

function historyRankLabel(item) {
  return item.rank ? `Pick #${item.rank} - ` : "";
}

function recordPaperLedgerTrade(item) {
  if (!item || item.rank !== 1) {
    return;
  }
  const entry = optionalNumber(item.entryPrice);
  const score = optionalNumber(item.score);
  if (!item.id || !item.symbol || !entry || entry <= 0 || score === null || score < PAPER_LEDGER_MIN_SCORE) {
    return;
  }

  const ledger = loadPaperLedger();
  const ledgerId = `ledger:${item.id}`;
  const tradeDay = historyItemDate(item);
  const normalizedSymbol = String(item.symbol).toUpperCase();
  if (ledger.some((trade) =>
    paperLedgerDay(trade) === tradeDay && String(trade.symbol || "").toUpperCase() === normalizedSymbol
  )) {
    return;
  }
  if (ledger.filter((trade) => paperLedgerDay(trade) === tradeDay).length >= PAPER_LEDGER_DAILY_TRADE_LIMIT) {
    return;
  }

  const openedAtIso = tradeDay === currentHostDate()
    ? new Date().toISOString()
    : item.timestamp?.iso || null;

  const trade = {
    id: ledgerId,
    sourceHistoryId: item.id,
    timestamp: item.timestamp,
    day: tradeDay,
    mode: item.mode,
    ticker: item.ticker,
    contract: item.contract,
    symbol: item.symbol,
    side: item.side,
    entryPrice: entry,
    entryGreeks: item.entryGreeks || null,
    quantity: 1,
    status: "open",
    score,
    openedAtIso,
    openHighlightAcknowledged: false,
    currentPrice: entry,
    highPrice: entry,
    lowPrice: entry,
    highTimestampIso: item.timestamp?.iso || null,
    lowTimestampIso: item.timestamp?.iso || null,
    openedReason: `${item.bias || "unknown"} ${item.permission || "trade permission"}`,
    decisionSnapshot: item.decisionSnapshot || null,
  };
  savePaperLedger([trade, ...ledger].slice(0, MAX_PAPER_LEDGER_ITEMS));
}

function renderPaperLedger({ preserveScroll = true } = {}) {
  if (preserveScroll) {
    return withViewportAnchor(() => renderPaperLedger({ preserveScroll: false }));
  }
  if (!fields.paperLedger) {
    return;
  }
  const selectedDate = replayDate.value || currentHostDate();
  const selectedTickers = getSelectedTickers();
  const isHistoricalDay = selectedDate !== currentHostDate();
  const sourceLedger = isHistoricalDay
    ? historicalPaperLedgerForDate(selectedDate)
    : loadPaperLedger();
  const ledger = sourceLedger.filter((trade) =>
    paperLedgerDay(trade) === selectedDate && (isHistoricalDay || matchesTickerFilter(trade, selectedTickers))
  );
  renderPaperLedgerSummary(ledger);
  renderDailyReportCard(ledger);

  if (ledger.length === 0) {
    const message = selectedDate
      ? `No simulated paper trades recorded on ${formatContractDate(selectedDate)}.`
      : "No simulated paper trades yet.";
    fields.paperLedgerOpen.textContent = message;
    fields.paperLedgerClosed.textContent = "No closed trades yet.";
    return;
  }
  if (isHistoricalDay) {
    refreshHistoricalPaperLedgerOutcomes(ledger, getReplayPoint());
  }

  const openTrades = ledger.filter((trade) => trade.status !== "closed");
  const closedTrades = ledger.filter((trade) => trade.status === "closed");
  renderPaperLedgerRows(fields.paperLedgerOpen, openTrades, { isHistoricalDay, state: "open" });
  renderPaperLedgerRows(fields.paperLedgerClosed, closedTrades, { isHistoricalDay, state: "closed" });
  scheduleLedgerHighlightExpiry(ledger, isHistoricalDay);
}

function renderPaperLedgerRows(container, trades, { isHistoricalDay, state }) {
  if (!container) {
    return;
  }
  if (trades.length === 0) {
    container.textContent = state === "open" ? "No open trades." : "No closed trades yet.";
    return;
  }
  container.innerHTML = "";
  for (const trade of trades) {
    const row = document.createElement("div");
    row.className = `paper-ledger-row contract-${trade.side || "call"} status-${trade.status || "open"}`;
    const highlight = paperLedgerHighlightState(trade, isHistoricalDay);
    if (highlight) {
      row.classList.add(`is-new-${highlight}`);
    }
    row.dataset.scrollKey = `ledger:${trade.id || trade.symbol || trade.timestamp?.iso || ""}`;
    const replayMinute = isHistoricalDay ? getReplayPoint().iso.slice(0, 16) : null;
    const cachedReplayOutcome = isHistoricalDay ? displayedHistoryOutcomes.get(trade.sourceHistoryId) : null;
    const replayOutcome = cachedReplayOutcome?.replayMinute === replayMinute ? cachedReplayOutcome : null;
    const replayOutcomeIsAuthoritative = replayOutcome?.source === "market-data option bars";
    const entry = optionalNumber(trade.entryPrice);
    const replayHigh = replayOutcomeIsAuthoritative ? optionalNumber(replayOutcome.high) : null;
    const displayedHigh = replayOutcomeIsAuthoritative
      ? Math.max(...[entry, replayHigh].filter((value) => value !== null))
      : (replayOutcome?.error ? entry : optionalNumber(trade.highPrice) ?? entry);
    const replayCurrent = replayOutcomeIsAuthoritative ? optionalNumber(replayOutcome.current) : null;
    const current = trade.status === "closed"
      ? optionalNumber(trade.exitPrice) ?? optionalNumber(trade.currentPrice) ?? entry
      : (replayOutcomeIsAuthoritative ? replayCurrent : optionalNumber(trade.currentPrice) ?? entry);
    const displayedTrade = { ...trade, currentPrice: current, highPrice: displayedHigh };
    const pnl = paperTradePnl(displayedTrade);
    const pnlPct = paperTradePnlPct(trade.entryPrice, trade.status === "closed" ? trade.exitPrice : current);
    const advisory = gexSellAdvisory(trade);
    const hasObservedLiveMark = trade.status === "closed" || isHistoricalDay || Boolean(trade.lastUpdatedIso);
    const highQualifier = hasObservedLiveMark
      ? "Observed market marks"
      : "Entry only - awaiting live mark";
    row.innerHTML = `
      <span class="ledger-contract">
        <strong>${trade.timestamp?.label || "-"}</strong>
        <em>${trade.contract || trade.symbol}</em>
      </span>
      <span class="history-pill">${trade.status === "closed" ? "Closed" : "Open"}</span>
      <span class="history-stat"><i>Entry</i><strong>${formatCurrency(trade.entryPrice)}</strong></span>
      <span class="history-stat"><i>Highest since entry</i><strong class="positive">${formatCurrency(displayedHigh ?? current)}</strong><small>${highQualifier}</small></span>
      <span class="history-stat"><i>${trade.status === "closed" ? "Exit" : "Now"}</i><strong>${formatCurrency(current)}</strong></span>
      <span class="history-stat"><i>P/L</i><strong class="${pnl >= 0 ? "positive" : "negative"}">${formatCurrency(pnl)}</strong></span>
      <span class="history-stat"><i>Move</i><strong class="${pnlPct >= 0 ? "positive" : "negative"}">${formatPercent(pnlPct)}</strong></span>
      <span class="history-stat"><i>GEX exit read</i><strong class="${advisory.className}">${advisory.label}</strong></span>
      ${highlight ? `<button class="ledger-ack" type="button" data-ledger-ack="${escapeHtml(trade.id)}" data-ledger-state="${highlight}">Acknowledge</button>` : ""}
      <details class="ledger-reason">
        <summary>Why the bot bought this contract</summary>
        ${tradeDecisionSnapshotMarkup(trade)}
      </details>
    `;
    container.appendChild(row);
  }
}

function paperLedgerHighlightState(trade, isHistoricalDay = false) {
  if (isHistoricalDay) {
    return null;
  }
  const closedAt = Date.parse(trade.closedAtIso || trade.exitTimestamp || "");
  if (trade.status === "closed" && !trade.closeHighlightAcknowledged && Number.isFinite(closedAt)
      && Date.now() - closedAt < PAPER_LEDGER_HIGHLIGHT_MS) {
    return "closed";
  }
  const openedAt = Date.parse(trade.openedAtIso || "");
  if (trade.status !== "closed" && !trade.openHighlightAcknowledged && Number.isFinite(openedAt)
      && Date.now() - openedAt < PAPER_LEDGER_HIGHLIGHT_MS) {
    return "open";
  }
  return null;
}

function acknowledgePaperLedgerHighlight(id, state) {
  if (!id) {
    return;
  }
  const ledger = loadPaperLedger().map((trade) => {
    if (trade.id !== id) {
      return trade;
    }
    return {
      ...trade,
      ...(state === "closed" ? { closeHighlightAcknowledged: true } : { openHighlightAcknowledged: true }),
    };
  });
  savePaperLedger(ledger);
  renderPaperLedger();
}

function scheduleLedgerHighlightExpiry(ledger, isHistoricalDay) {
  if (ledgerHighlightTimer !== null) {
    clearTimeout(ledgerHighlightTimer);
    ledgerHighlightTimer = null;
  }
  if (isHistoricalDay) {
    return;
  }
  const expiries = ledger.flatMap((trade) => {
    const timestamp = trade.status === "closed"
      ? Date.parse(trade.closedAtIso || trade.exitTimestamp || "")
      : Date.parse(trade.openedAtIso || "");
    return paperLedgerHighlightState(trade, false) && Number.isFinite(timestamp)
      ? [timestamp + PAPER_LEDGER_HIGHLIGHT_MS]
      : [];
  });
  if (expiries.length === 0) {
    return;
  }
  const delay = Math.max(50, Math.min(...expiries) - Date.now() + 50);
  ledgerHighlightTimer = setTimeout(() => renderPaperLedger(), delay);
}

function refreshHistoricalPaperLedgerOutcomes(ledger, replayPoint) {
  const replayMinute = replayPoint.iso.slice(0, 16);
  const pending = ledger.filter((trade) =>
    trade.sourceHistoryId && displayedHistoryOutcomes.get(trade.sourceHistoryId)?.replayMinute !== replayMinute
  );
  if (pending.length === 0) {
    return;
  }
  const requestKey = `${replayMinute}:${pending.map((trade) => trade.sourceHistoryId).sort().join(",")}`;
  if (historicalLedgerOutcomeRequests.has(requestKey)) {
    return;
  }
  historicalLedgerOutcomeRequests.add(requestKey);
  const historyItems = pending.map((trade) => {
    const contract = trade.decisionSnapshot?.contract || {};
    return {
      id: trade.sourceHistoryId,
      symbol: trade.symbol,
      ticker: trade.ticker,
      underlying: trade.ticker,
      timestamp: trade.timestamp,
      entryPrice: trade.entryPrice,
      entryGreeks: trade.entryGreeks,
      expirationDate: contract.expiration,
      strikePrice: contract.strike,
      contractType: trade.side || contract.type,
    };
  });
  fetchTradeHistoryOutcomes(historyItems, replayPoint)
    .then((outcomes) => {
      for (const [id, outcome] of Object.entries(outcomes)) {
        displayedHistoryOutcomes.set(id, { ...outcome, replayMinute });
      }
      if (Number(replayTime.value) >= Number(replayTime.max)) {
        updatePaperLedgerExtremesFromOutcomes(outcomes);
      } else {
        renderPaperLedger();
      }
    })
    .catch((error) => {
      historicalLedgerOutcomeRequests.delete(requestKey);
      console.warn("Could not load historical paper-ledger outcomes from SQLite.", error);
    });
}

function renderPaperLedgerSummary(ledger) {
  if (!fields.ledgerRealized) {
    return;
  }
  const closed = ledger.filter((trade) => trade.status === "closed");
  const open = ledger.filter((trade) => trade.status !== "closed");
  const realized = closed.reduce((sum, trade) => sum + paperTradePnl(trade), 0);
  const openPl = open.reduce((sum, trade) => sum + paperTradePnl(trade), 0);
  const wins = closed.filter((trade) => paperTradePnl(trade) > 0).length;
  const winRate = closed.length > 0 ? wins / closed.length : null;

  fields.ledgerRealized.textContent = formatCurrency(realized);
  fields.ledgerRealized.classList.toggle("positive", realized >= 0);
  fields.ledgerRealized.classList.toggle("negative", realized < 0);
  fields.ledgerOpenPl.textContent = formatCurrency(openPl);
  fields.ledgerOpenPl.classList.toggle("positive", openPl >= 0);
  fields.ledgerOpenPl.classList.toggle("negative", openPl < 0);
  fields.ledgerClosedCount.textContent = String(closed.length);
  fields.ledgerOpenCount.textContent = String(open.length);
  fields.ledgerWinRate.textContent = winRate === null ? "-" : formatPercent(winRate);
}

function renderDailyReportCard(ledger) {
  if (!fields.reportTotalTrades) {
    return;
  }
  const trades = [...ledger].sort((a, b) =>
    String(a.timestamp?.iso || "").localeCompare(String(b.timestamp?.iso || ""))
  );
  const results = trades.map((trade) => ({ trade, pnl: paperTradePnl(trade) }));
  const wins = results.filter((result) => result.pnl > 0);
  const losses = results.filter((result) => result.pnl < 0);
  const grossProfit = wins.reduce((sum, result) => sum + result.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((sum, result) => sum + result.pnl, 0));
  const totalPnl = results.reduce((sum, result) => sum + result.pnl, 0);
  const tickerPnl = new Map();
  let equity = 0;
  let peak = 0;
  let maxDrawdown = 0;

  for (const result of results) {
    equity += result.pnl;
    peak = Math.max(peak, equity);
    maxDrawdown = Math.max(maxDrawdown, peak - equity);
    const ticker = result.trade.ticker || contractUnderlying(result.trade) || "Unknown";
    tickerPnl.set(ticker, (tickerPnl.get(ticker) || 0) + result.pnl);
  }

  const rankedTickers = [...tickerPnl.entries()].sort((a, b) => b[1] - a[1]);
  fields.reportTotalTrades.textContent = String(trades.length);
  fields.reportWinRate.textContent = trades.length ? formatPercent(wins.length / trades.length) : "-";
  fields.reportAverageWin.textContent = wins.length
    ? formatSignedCurrency(grossProfit / wins.length)
    : "-";
  fields.reportAverageLoss.textContent = losses.length
    ? formatSignedCurrency(-grossLoss / losses.length)
    : "-";
  fields.reportProfitFactor.textContent = grossLoss > 0
    ? (grossProfit / grossLoss).toFixed(2)
    : grossProfit > 0 ? "Unlimited" : "-";
  fields.reportMaxDrawdown.textContent = formatCurrency(maxDrawdown);
  fields.reportBestTicker.textContent = rankedTickers.length
    ? `${rankedTickers[0][0]} ${formatSignedCurrency(rankedTickers[0][1])}`
    : "-";
  fields.reportWorstTicker.textContent = rankedTickers.length
    ? `${rankedTickers[rankedTickers.length - 1][0]} ${formatSignedCurrency(rankedTickers[rankedTickers.length - 1][1])}`
    : "-";
  fields.reportProfitable.textContent = trades.length
    ? `${totalPnl > 0 ? "Yes" : totalPnl < 0 ? "No" : "Break-even"} (${formatSignedCurrency(totalPnl)})`
    : "No trades yet";
  fields.reportProfitable.classList.toggle("positive", totalPnl > 0);
  fields.reportProfitable.classList.toggle("negative", totalPnl < 0);
}

function tradeDecisionSnapshotMarkup(trade) {
  const snapshot = trade.decisionSnapshot;
  if (!snapshot) {
    return `<p>No reason snapshot was saved for this older ledger entry.</p>`;
  }
  const gex = snapshot.gex || {};
  const technicals = snapshot.technicals || {};
  const contract = snapshot.contract || {};
  const reasons = Array.isArray(technicals.reasons) && technicals.reasons.length
    ? technicals.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")
    : "<li>No technical explanations were available.</li>";
  return `
    <div class="ledger-reason-grid">
      <div><span>GEX bias</span><strong>${escapeHtml(gex.bias || "n/a")}</strong></div>
      <div><span>GEX score</span><strong>${formatOptionalNumber(gex.score)}</strong></div>
      <div><span>Spot / zero gamma</span><strong>${formatOptionalNumber(gex.spot)} / ${formatOptionalNumber(gex.zeroGamma)}</strong></div>
      <div><span>VWAP</span><strong>${formatOptionalNumber(technicals.vwap)}</strong></div>
      <div><span>50 / 200-day MA</span><strong>${formatOptionalNumber(technicals.sma50)} / ${formatOptionalNumber(technicals.sma200)}</strong></div>
      <div><span>Contract score</span><strong>${formatOptionalNumber(contract.rankingScore)}</strong></div>
      <div><span>Spread</span><strong>${formatPercent(contract.spreadPercent)}</strong></div>
      <div><span>Open interest / volume</span><strong>${formatOptionalNumber(contract.openInterest)} / ${formatOptionalNumber(contract.volume)}</strong></div>
      <div><span>Entry Greeks</span><strong>${formatGreek("delta", contract.delta)} ${formatGreek("gamma", contract.gamma)} ${formatGreek("iv", contract.impliedVolatility)}</strong></div>
    </div>
    <ul>${reasons}</ul>
  `;
}

function updatePaperLedgerPrices(priceMap, asOfIso = null, { evaluateExit = true } = {}) {
  const ledger = loadPaperLedger();
  let changed = false;
  const now = asOfIso ? new Date(asOfIso) : new Date();
  const updated = ledger.map((trade) => {
    if (trade.status === "closed") {
      return trade;
    }
    const current = reliableOptionMark(priceMap?.[trade.symbol]);
    if (!current || current <= 0) {
      return trade;
    }
    const entry = optionalNumber(trade.entryPrice);
    if (!entry || entry <= 0) {
      return trade;
    }
    const previousHigh = optionalNumber(trade.highPrice) ?? entry;
    const previousLow = optionalNumber(trade.lowPrice) ?? entry;
    const madeHigh = current > previousHigh;
    const madeLow = current < previousLow;
    if (!evaluateExit) {
      changed = true;
      return {
        ...trade,
        currentPrice: current,
        highPrice: madeHigh ? current : previousHigh,
        lowPrice: madeLow ? current : previousLow,
        highTimestampIso: madeHigh ? now.toISOString() : trade.highTimestampIso || trade.timestamp?.iso || null,
        lowTimestampIso: madeLow ? now.toISOString() : trade.lowTimestampIso || trade.timestamp?.iso || null,
        lastUpdatedIso: now.toISOString(),
      };
    }
    const decision = gexSellDecision(trade);
    const sameSignal = decision.shouldExit && trade.exitSignalKey === decision.key;
    const previousSignalTime = Date.parse(trade.exitSignalTimestamp || "");
    const distinctRefresh = !Number.isFinite(previousSignalTime) || now.getTime() - previousSignalTime >= 5000;
    const exitSignalCount = decision.shouldExit
      ? (sameSignal ? Number(trade.exitSignalCount || 0) + (distinctRefresh ? 1 : 0) : 1)
      : 0;
    const shouldClose = decision.shouldExit && exitSignalCount >= EXIT_CONFIRMATION_REFRESHES;
    const next = {
      ...trade,
      status: shouldClose ? "closed" : "open",
      currentPrice: current,
      highPrice: madeHigh ? current : previousHigh,
      lowPrice: madeLow ? current : previousLow,
      highTimestampIso: madeHigh ? now.toISOString() : trade.highTimestampIso || trade.timestamp?.iso || null,
      lowTimestampIso: madeLow ? now.toISOString() : trade.lowTimestampIso || trade.timestamp?.iso || null,
      lastUpdatedIso: now.toISOString(),
      exitSignalKey: decision.shouldExit ? decision.key : null,
      exitSignalCount,
      exitSignalLabel: decision.shouldExit ? decision.label : null,
      exitSignalTimestamp: decision.shouldExit
        ? (distinctRefresh || !sameSignal ? now.toISOString() : trade.exitSignalTimestamp)
        : null,
    };
    if (shouldClose) {
      next.exitPrice = current;
      next.exitTimestamp = now.toISOString();
      next.closedAtIso = now.toISOString();
      next.closeHighlightAcknowledged = false;
      next.exitReason = decision.label;
    }
    changed = true;
    return next;
  });

  if (changed) {
    savePaperLedger(updated);
    renderPaperLedger();
  }
}

function reliableOptionMark(priceRow) {
  if (!priceRow || typeof priceRow !== "object") {
    return null;
  }
  const bid = optionalNumber(priceRow.bid);
  const ask = optionalNumber(priceRow.ask);
  const last = optionalNumber(priceRow.last);
  const mid = optionalNumber(priceRow.mid);
  if (bid !== null && ask !== null && bid > 0 && ask >= bid) {
    const quoteMid = (bid + ask) / 2;
    const spreadRatio = quoteMid > 0 ? (ask - bid) / quoteMid : Infinity;
    if (spreadRatio > 0.50) {
      return last !== null && last > 0 ? last : null;
    }
  }
  return mid !== null && mid > 0 ? mid : (last !== null && last > 0 ? last : null);
}

function paperTradePnl(trade) {
  const entry = optionalNumber(trade.entryPrice);
  const exit = optionalNumber(trade.status === "closed" ? trade.exitPrice : trade.currentPrice);
  const quantity = optionalNumber(trade.quantity) || 1;
  if (!entry || !exit) {
    return 0;
  }
  return (exit - entry) * OPTION_CONTRACT_MULTIPLIER * quantity;
}

function paperTradePnlPct(entryPrice, currentPrice) {
  const entry = optionalNumber(entryPrice);
  const current = optionalNumber(currentPrice);
  if (!entry || !current) {
    return 0;
  }
  return (current - entry) / entry;
}

function clearPaperLedgerForSelectedDay() {
  const selectedDate = replayDate.value || currentHostDate();
  const remaining = loadPaperLedger().filter((trade) => paperLedgerDay(trade) !== selectedDate);
  savePaperLedger(remaining);
  if (persistentHistoryByDate.has(selectedDate)) {
    persistentHistoryByDate.get(selectedDate).paperLedger = [];
  }
  deletePersistentStorageDay("paper_ledger", selectedDate);
  setStatus(`Cleared simulated paper ledger for ${formatContractDate(selectedDate)}.`, false);
}

function paperLedgerDay(trade) {
  return trade.day || trade.timestamp?.day || String(trade.timestamp?.iso || "").slice(0, 10);
}

function clearTradeHistoryForSelectedDay() {
  const selectedDate = replayDate.value || currentHostDate();
  const remaining = loadTradeHistory().filter((item) => historyItemDate(item) !== selectedDate);
  saveTradeHistory(remaining);
  if (persistentHistoryByDate.has(selectedDate)) {
    persistentHistoryByDate.get(selectedDate).tradeHistory = [];
  }
  deletePersistentStorageDay("trade_history", selectedDate);
  setStatus(`Cleared trade-permission picks for ${formatContractDate(selectedDate)}.`, false);
}

async function downloadTradeHistoryForSelectedDay() {
  const selectedDate = replayDate.value || currentHostDate();
  if (selectedDate !== currentHostDate()) {
    await ensureHistoricalDateLoaded(selectedDate);
  }
  const history = selectedDate === currentHostDate()
    ? loadTradeHistory().filter((item) => historyItemDate(item) === selectedDate)
    : historicalTradeHistoryForDate(selectedDate);
  await downloadTradeHistoryItems({
    history,
    emptyMessage: `No trade-permission picks to download for ${formatContractDate(selectedDate)}.`,
    filename: `trade-permissions-${selectedDate}.csv`,
    label: formatContractDate(selectedDate),
  });
}

async function downloadTradeHistoryForRange() {
  const startDate = historyStartDate?.value || replayDate.value || currentHostDate();
  const endDate = historyEndDate?.value || startDate;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    setStatus("Choose a valid From and To date before downloading the range.", true);
    return;
  }
  const from = startDate <= endDate ? startDate : endDate;
  const to = startDate <= endDate ? endDate : startDate;
  const tickers = parseTickerFilter(historyTickers?.value || "");
  const history = tradeHistoryForRange(from, to, tickers);
  const tickerLabel = tickers.length > 0 ? `-${tickers.join("-")}` : "";
  await downloadTradeHistoryItems({
    history,
    emptyMessage: `No trade-permission picks found from ${formatContractDate(from)} to ${formatContractDate(to)}${tickers.length ? ` for ${tickers.join(", ")}` : ""}.`,
    filename: `trade-permissions-${from}-to-${to}${tickerLabel}.csv`,
    label: `${formatContractDate(from)} to ${formatContractDate(to)}`,
    refreshOutcomes: false,
  });
}

async function downloadTradeHistoryItems({ history, emptyMessage, filename, label, refreshOutcomes = true }) {
  if (history.length === 0) {
    setStatus(emptyMessage, true);
    setHistoryExportStatus(emptyMessage, true);
    return;
  }

  const savedOutcomes = mergeOutcomeFallbacks(history, {});
  const missingHistory = refreshOutcomes
    ? history.filter((item) => !hasCompleteOutcome(savedOutcomes[item.id]))
    : [];
  setStatus(
    missingHistory.length > 0
      ? `Refreshing missing outcome data for ${missingHistory.length} of ${history.length} saved picks...`
      : `Preparing ${history.length} saved picks...`,
    false
  );
  let refreshedOutcomes = {};
  try {
    if (missingHistory.length > 0) {
      refreshedOutcomes = await fetchTradeHistoryOutcomes(missingHistory);
    }
  } catch (_error) {
    setStatus("Could not refresh high/low outcomes. Downloading saved values instead.", true);
  }
  const mergedOutcomes = mergeOutcomeFallbacks(history, { ...savedOutcomes, ...refreshedOutcomes });
  const hydrated = history.map((item) => mergedOutcomes[item.id] ? { ...item, outcome: mergedOutcomes[item.id] } : item);
  saveTradeHistoryOutcomes(mergedOutcomes);
  const csv = tradeHistoryCsv(hydrated);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Safari may cancel a download when its object URL is revoked in the same task.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  setStatus(`Downloaded ${hydrated.length} trade-permission picks for ${label}.`, false);
  setHistoryExportStatus(`Downloaded ${hydrated.length} saved picks for ${label}.`, false);
}

function tradeHistoryForRange(from, to, tickers) {
  return loadTradeHistory().filter((item) => {
    const day = historyItemDate(item);
    return day >= from && day <= to && matchesTickerFilter(item, tickers);
  });
}

function updateHistoryRangeCount() {
  const startDate = historyStartDate?.value || "";
  const endDate = historyEndDate?.value || startDate;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    setHistoryExportStatus("Choose both a From and To date.", false);
    return;
  }
  const from = startDate <= endDate ? startDate : endDate;
  const to = startDate <= endDate ? endDate : startDate;
  const tickers = parseTickerFilter(historyTickers?.value || "");
  const count = tradeHistoryForRange(from, to, tickers).length;
  const tickerText = tickers.length > 0 ? ` for ${tickers.join(", ")}` : "";
  setHistoryExportStatus(
    `${count} saved trade-permission pick${count === 1 ? "" : "s"} from ${formatContractDate(from)} to ${formatContractDate(to)}${tickerText}.`,
    count === 0
  );
}

function setHistoryExportStatus(message, isError) {
  if (!historyExportStatus) {
    return;
  }
  historyExportStatus.textContent = message;
  historyExportStatus.classList.toggle("error", Boolean(isError));
}

function hasCompleteOutcome(outcome) {
  return Boolean(
    outcome &&
    !outcome.error &&
    Number.isFinite(optionalNumber(outcome.high)) &&
    Number.isFinite(optionalNumber(outcome.low))
  );
}

function tradeHistoryCsv(history) {
  const header = [
    "time",
    "rank",
    "ticker",
    "contract",
    "symbol",
    "side",
    "recorded_price",
    "highest_after_buy",
    "highest_delta",
    "highest_gamma",
    "highest_iv",
    "outcome_status",
    "bias",
    "permission",
    "score",
    "mode",
    "gex_score_at_buy",
    "spot_at_buy",
    "zero_gamma_at_buy",
    "vwap_at_buy",
    "sma_50_at_buy",
    "sma_200_at_buy",
    "contract_spread_pct_at_buy",
    "contract_open_interest_at_buy",
    "contract_volume_at_buy",
    "buy_reason_snapshot",
  ];
  const rows = history.map((item) => [
    item.timestamp?.label || "",
    item.rank || "",
    item.ticker || "",
    item.contract || "",
    item.symbol || "",
    item.side || "",
    item.entryPrice ?? "",
    item.outcome?.high ?? "",
    item.outcome?.high_greeks?.delta ?? "",
    item.outcome?.high_greeks?.gamma ?? "",
    item.outcome?.high_greeks?.implied_volatility ?? "",
    outcomeStatus(item.outcome),
    item.bias || "",
    item.permission || "",
    item.score ?? "",
    item.mode || "",
    item.decisionSnapshot?.gex?.score ?? "",
    item.decisionSnapshot?.gex?.spot ?? "",
    item.decisionSnapshot?.gex?.zeroGamma ?? "",
    item.decisionSnapshot?.technicals?.vwap ?? "",
    item.decisionSnapshot?.technicals?.sma50 ?? "",
    item.decisionSnapshot?.technicals?.sma200 ?? "",
    item.decisionSnapshot?.contract?.spreadPercent ?? "",
    item.decisionSnapshot?.contract?.openInterest ?? "",
    item.decisionSnapshot?.contract?.volume ?? "",
    item.decisionSnapshot ? JSON.stringify(item.decisionSnapshot) : "",
  ]);
  return [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}

function parseTickerFilter(value) {
  return [...new Set(
    String(value || "")
      .split(",")
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean)
  )];
}

function matchesTickerFilter(item, tickers) {
  if (tickers.length === 0) {
    return true;
  }
  const ticker = String(item.ticker || "").toUpperCase();
  const underlying = String(item.underlying || "").toUpperCase();
  const symbol = String(item.symbol || "").toUpperCase();
  return tickers.some((filter) => ticker === filter || underlying === filter || symbol.startsWith(filter));
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

async function updateTradeHistoryOutcomes(history, { replayPoint = null, persist = true } = {}) {
  const historyById = new Map(history.map((item) => [item.id, item]));
  const requestKey = `${historyItemDate(history[0] || {})}:${historyItemTicker(history[0] || {})}`;
  const requestVersion = (historyOutcomeRequestVersions.get(requestKey) || 0) + 1;
  historyOutcomeRequestVersions.set(requestKey, requestVersion);
  try {
    const outcomes = await fetchTradeHistoryOutcomes(history, replayPoint);
    if (historyOutcomeRequestVersions.get(requestKey) !== requestVersion) {
      return;
    }
    // Historical replay must never replace a failed as-of query with entry
    // prices; doing so makes a previously reached high appear to disappear.
    const mergedOutcomes = replayPoint ? outcomes : mergeOutcomeFallbacks(history, outcomes);
    const replayMinute = replayPoint?.iso?.slice(0, 16) || null;
    for (const [id, outcome] of Object.entries(mergedOutcomes)) {
      displayedHistoryOutcomes.set(id, { ...outcome, replayMinute });
    }
    if (persist) {
      saveTradeHistoryOutcomes(mergedOutcomes);
      updatePaperLedgerExtremesFromOutcomes(mergedOutcomes);
    }
    for (const row of fields.tradeHistory.querySelectorAll(".trade-history-row")) {
      const id = row.dataset.historyId;
      const item = historyById.get(id);
      if (!item) {
        continue;
      }
      renderHistoryOutcome(row, mergedOutcomes[id], item);
    }
    if (replayPoint) {
      renderPaperLedger();
    }
  } catch (error) {
    if (historyOutcomeRequestVersions.get(requestKey) !== requestVersion) {
      return;
    }
    const fallbackOutcomes = replayPoint
      ? Object.fromEntries(history.map((item) => [item.id, {
          error: `Historical replay unavailable after retry: ${error?.message || error}`,
        }]))
      : mergeOutcomeFallbacks(history, {});
    const replayMinute = replayPoint?.iso?.slice(0, 16) || null;
    for (const [id, outcome] of Object.entries(fallbackOutcomes)) {
      displayedHistoryOutcomes.set(id, { ...outcome, replayMinute });
    }
    if (persist) {
      saveTradeHistoryOutcomes(fallbackOutcomes);
      updatePaperLedgerExtremesFromOutcomes(fallbackOutcomes);
    }
    for (const row of fields.tradeHistory.querySelectorAll(".trade-history-row")) {
      const item = historyById.get(row.dataset.historyId);
      if (!item) {
        continue;
      }
      renderHistoryOutcome(
        row,
        fallbackOutcomes[row.dataset.historyId] || null,
        item
      );
    }
    if (replayPoint) {
      renderPaperLedger();
    }
  }
}

function updatePaperLedgerExtremesFromOutcomes(outcomes) {
  const ledger = loadPaperLedger();
  let changed = false;
  const updated = ledger.map((trade) => {
    const outcome = outcomes?.[trade.sourceHistoryId];
    if (!outcome || outcome.error) {
      return trade;
    }
    const high = optionalNumber(outcome.high);
    const low = optionalNumber(outcome.low);
    const current = optionalNumber(outcome.current);
    const entry = optionalNumber(trade.entryPrice);
    const previousHigh = optionalNumber(trade.highPrice) ?? optionalNumber(trade.entryPrice);
    const previousLow = optionalNumber(trade.lowPrice) ?? optionalNumber(trade.entryPrice);
    const authoritative = outcome.source === "market-data option bars";
    const authoritativeHighs = [entry, high].filter((value) => value !== null);
    const authoritativeLows = [entry, low].filter((value) => value !== null);
    const nextHigh = authoritative
      ? (authoritativeHighs.length ? Math.max(...authoritativeHighs) : previousHigh)
      : (high !== null && (previousHigh === null || high > previousHigh) ? high : previousHigh);
    const nextLow = authoritative
      ? (authoritativeLows.length ? Math.min(...authoritativeLows) : previousLow)
      : (low !== null && (previousLow === null || low < previousLow) ? low : previousLow);
    const nextCurrent = authoritative && trade.status !== "closed" && current !== null
      ? current
      : trade.currentPrice;
    if (nextHigh === previousHigh && nextLow === previousLow && nextCurrent === trade.currentPrice) {
      return trade;
    }
    changed = true;
    return {
      ...trade,
      highPrice: nextHigh,
      lowPrice: nextLow,
      currentPrice: nextCurrent,
      highTimestampIso: authoritative || nextHigh !== previousHigh
        ? (nextHigh === entry ? trade.timestamp?.iso : outcome.high_time) || trade.highTimestampIso
        : trade.highTimestampIso,
      lowTimestampIso: authoritative || nextLow !== previousLow
        ? (nextLow === entry ? trade.timestamp?.iso : outcome.low_time) || trade.lowTimestampIso
        : trade.lowTimestampIso,
      lastUpdatedIso: authoritative && outcome.current_time
        ? outcome.current_time
        : trade.lastUpdatedIso,
    };
  });
  if (changed) {
    savePaperLedger(updated);
    renderPaperLedger();
  }
}

function mergeOutcomeFallbacks(history, outcomes) {
  const merged = { ...outcomes };
  const allHistory = loadTradeHistory();
  for (const item of history) {
    const existing = merged[item.id] || item.outcome;
    if (existing && !existing.error && existing.high !== undefined && existing.low !== undefined) {
      merged[item.id] = existing;
      continue;
    }
    const fallback = savedSignalOutcomeFallback(item, allHistory);
    if (fallback) {
      merged[item.id] = fallback;
    } else if (existing) {
      merged[item.id] = existing;
    }
  }
  return merged;
}

function savedSignalOutcomeFallback(item, allHistory) {
  const symbol = String(item.symbol || "").toUpperCase();
  const day = historyItemDate(item);
  const entryIso = item.timestamp?.iso || "";
  if (!symbol || !day || !entryIso) {
    return null;
  }

  const comparable = allHistory
    .filter((candidate) => {
      const candidatePrice = optionalNumber(candidate.entryPrice);
      return (
        String(candidate.symbol || "").toUpperCase() === symbol &&
        historyItemDate(candidate) === day &&
        candidate.timestamp?.iso &&
        candidate.timestamp.iso >= entryIso &&
        candidatePrice !== null &&
        Number.isFinite(candidatePrice)
      );
    })
    .sort((a, b) => String(a.timestamp?.iso || "").localeCompare(String(b.timestamp?.iso || "")));

  if (comparable.length === 0) {
    return null;
  }

  const highItem = comparable.reduce((best, current) =>
    Number(current.entryPrice) > Number(best.entryPrice) ? current : best
  );
  const lowItem = comparable.reduce((best, current) =>
    Number(current.entryPrice) < Number(best.entryPrice) ? current : best
  );
  const entryPrice = optionalNumber(item.entryPrice);
  const high = optionalNumber(highItem.entryPrice);
  const low = optionalNumber(lowItem.entryPrice);
  return {
    high,
    high_time: highItem.timestamp?.iso || null,
    high_greeks: greeksFromHistoryItem(highItem),
    low,
    low_time: lowItem.timestamp?.iso || null,
    low_greeks: greeksFromHistoryItem(lowItem),
    went_up: high !== null && entryPrice !== null ? high > entryPrice : false,
    source: "saved signal prices fallback",
  };
}

function greeksFromHistoryItem(item) {
  const greeks = item.entryGreeks || {};
  const delta = optionalNumber(greeks.delta);
  const gamma = optionalNumber(greeks.gamma);
  const iv = optionalNumber(greeks.implied_volatility);
  if (delta === null && gamma === null && iv === null) {
    return null;
  }
  return {
    delta,
    gamma,
    implied_volatility: iv,
    estimated: Boolean(greeks.estimated),
  };
}

async function fetchTradeHistoryOutcomes(history, replayPoint = null) {
  const entries = history
    .filter((item) => item.symbol && item.timestamp?.iso)
    .map((item) => ({
      id: item.id,
      symbol: item.symbol,
      date: historyItemDate(item),
      timestamp_iso: item.timestamp.iso,
      underlying: item.underlying || item.ticker || contractUnderlying({ symbol: item.symbol }),
      expiration_date: item.expirationDate,
      strike_price: item.strikePrice,
      contract_type: item.contractType || item.side,
      entry_price: item.entryPrice,
      entry_spot: item.entrySpot,
      entry_iv: item.entryGreeks?.implied_volatility,
      fallback_path: item.pricePath || [],
      fallback_delta: item.entryGreeks?.delta,
      fallback_gamma: item.entryGreeks?.gamma,
      as_of_time: replayPoint?.marketClock || null,
      as_of_iso: replayPoint?.iso || null,
    }));
  if (entries.length === 0) {
    return {};
  }

  const outcomes = {};
  const cacheMinute = replayPoint?.iso ? replayPoint.iso.slice(0, 16) : null;
  const pendingEntries = [];
  for (const entry of entries) {
    const cacheKey = cacheMinute ? `${entry.id}|${cacheMinute}` : null;
    if (cacheKey && replayOutcomeCache.has(cacheKey)) {
      outcomes[entry.id] = replayOutcomeCache.get(cacheKey);
    } else {
      pendingEntries.push(entry);
    }
  }
  // One historical ticker can contain hundreds of repeated confirmations but
  // usually only a few dozen contracts. Keep them together so the backend can
  // deduplicate symbols and load each completed-day series once.
  const outcomeBatchSize = replayPoint ? 1000 : 100;
  for (let index = 0; index < pendingEntries.length; index += outcomeBatchSize) {
    const batch = pendingEntries.slice(index, index + outcomeBatchSize);
    const payload = await postJsonWithRetry("/api/options/outcomes", {
      entries: batch,
      local_only: Boolean(replayPoint),
    }, 3);
    Object.assign(outcomes, payload.outcomes || {});
    if (cacheMinute) {
      for (const entry of batch) {
        const outcome = payload.outcomes?.[entry.id];
        if (outcome && !outcome.error && optionalNumber(outcome.current) !== null) {
          replayOutcomeCache.set(`${entry.id}|${cacheMinute}`, outcome);
        }
      }
    }
  }
  while (replayOutcomeCache.size > 4000) {
    replayOutcomeCache.delete(replayOutcomeCache.keys().next().value);
  }
  return outcomes;
}

async function postJsonWithRetry(url, body, attempts = 2) {
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await postJson(url, body);
    } catch (error) {
      lastError = error;
      if (attempt < attempts) {
        await new Promise((resolve) => setTimeout(resolve, attempt * 250));
      }
    }
  }
  throw lastError || new Error("Request failed after retry.");
}

function saveTradeHistoryOutcomes(outcomes) {
  const history = loadTradeHistory();
  let changed = false;
  const updated = history.map((item) => {
    const outcome = outcomes[item.id];
    if (!outcome) {
      return item;
    }
    changed = true;
    return { ...item, outcome };
  });
  if (changed) {
    saveTradeHistory(updated);
  }
}

function renderHistoryOutcome(row, outcome, item = null) {
  const highEl = row.querySelector(".history-high");
  const highTimeEl = row.querySelector(".history-high-time");
  const highGreeksEl = row.querySelector(".history-high-greeks");
  if (!highEl || !highGreeksEl) {
    return;
  }
  if (!outcome || outcome.error) {
    highEl.textContent = "n/a";
    if (highTimeEl) {
      highTimeEl.textContent = "Time unavailable";
    }
    highGreeksEl.textContent = outcome?.error || "No outcome data";
    const currentEl = row.querySelector(".history-current");
    const currentTimeEl = row.querySelector(".history-current-time");
    const changeEl = row.querySelector(".history-change");
    if (currentEl) currentEl.textContent = "n/a";
    if (currentTimeEl) currentTimeEl.textContent = "Time unavailable";
    if (changeEl) changeEl.textContent = "n/a";
    return;
  }

  highEl.textContent = outcome.went_up ? formatCurrency(outcome.high) : `No rise ${formatCurrency(outcome.high)}`;
  if (highTimeEl) {
    highTimeEl.textContent = outcome.high_time ? `Hit ${formatOutcomeTimestamp(outcome.high_time)}` : "Time unavailable";
  }
  renderGreekOutcomeSummary(highGreeksEl, outcome.high_greeks);
  const current = optionalNumber(outcome.current);
  const entryPrice = optionalNumber(row.dataset.entryPrice);
  const currentEl = row.querySelector(".history-current");
  const currentTimeEl = row.querySelector(".history-current-time");
  const changeEl = row.querySelector(".history-change");
  const exitEl = row.querySelector(".history-exit");
  if (currentEl && changeEl && current !== null) {
    currentEl.textContent = formatCurrency(current);
    if (currentTimeEl) {
      const ageLabel = formatBarAge(outcome.current_age_seconds);
      const staleLabel = outcome.current_is_stale ? "stale · " : "";
      currentTimeEl.textContent = outcome.current_time
        ? `${formatOutcomeTimestamp(outcome.current_time)}${ageLabel ? ` · ${staleLabel}${ageLabel}` : ""}`
        : "Latest available trade";
      currentTimeEl.classList.toggle("stale", Boolean(outcome.current_is_stale));
    }
    if (entryPrice) {
      const change = (current - entryPrice) / entryPrice;
      changeEl.textContent = formatPercent(change);
      changeEl.classList.toggle("positive", change >= 0);
      changeEl.classList.toggle("negative", change < 0);
    }
  } else if (currentEl && changeEl) {
    currentEl.textContent = "n/a";
    if (currentTimeEl) currentTimeEl.textContent = "Time unavailable";
    changeEl.textContent = "n/a";
  }
  if (exitEl && item) {
    const exitPlan = gexSellAdvisory(item);
    exitEl.textContent = exitPlan.label;
    exitEl.classList.toggle("positive", exitPlan.className === "positive");
    exitEl.classList.toggle("negative", exitPlan.className === "negative");
  }
}

function formatBarAge(value) {
  const seconds = optionalNumber(value);
  if (seconds === null || seconds < 0) {
    return "";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s old`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return remainder ? `${minutes}m ${remainder}s old` : `${minutes}m old`;
}

function formatOutcomeTimestamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value || "-");
  }
  return parsed.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function outcomeStatus(outcome) {
  if (!outcome) {
    return "not refreshed";
  }
  if (outcome.error) {
    return outcome.error;
  }
  if (outcome.source) {
    return outcome.source;
  }
  return "market-data option bars";
}

function greekOutcomeSummary(greeks) {
  if (!greeks) {
    return "Greeks n/a";
  }
  const suffix = greeks.estimated ? " est" : "";
  return `${formatGreek("delta", greeks.delta)} ${formatGreek("gamma", greeks.gamma)} ${formatGreek("iv", greeks.implied_volatility)}${suffix}`;
}

function renderGreekOutcomeSummary(container, greeks) {
  container.replaceChildren();
  if (!greeks) {
    container.textContent = "Greeks n/a";
    return;
  }
  const values = [
    ["Delta", formatGreekValue("delta", greeks.delta)],
    ["Gamma", formatGreekValue("gamma", greeks.gamma)],
    ["IV", formatGreekValue("iv", greeks.implied_volatility)],
  ];
  values.forEach(([label, value]) => {
    const part = document.createElement("span");
    part.className = "history-greek";
    part.textContent = `${label} ${value}`;
    container.appendChild(part);
  });
  if (greeks.estimated) {
    const estimate = document.createElement("span");
    estimate.className = "history-greek-estimate";
    estimate.textContent = "estimated";
    container.appendChild(estimate);
  }
}

async function updateTradeHistoryPrices(history, { historicalAsOf = null } = {}) {
  const symbols = [...new Set(history.map((item) => item.symbol).filter(Boolean))];
  if (symbols.length === 0) {
    return;
  }

  try {
    const query = new URLSearchParams({ symbols: symbols.join(",") });
    if (historicalAsOf && replayDate.value) {
      query.set("date", replayDate.value);
      query.set("time", historicalAsOf);
    }
    const payload = await getJson(`/api/options/prices?${query.toString()}`);
    updatePaperLedgerPrices(payload.prices || {});
    const savedHistoryById = new Map(loadTradeHistory().map((item) => [item.id, item]));
    const historyById = new Map(history.map((item) => [item.id, item]));
    for (const row of fields.tradeHistory.querySelectorAll(".trade-history-row")) {
      const item = historyById.get(row.dataset.historyId);
      if (!item) {
        continue;
      }
      const symbol = row.dataset.symbol;
      const entryPrice = optionalNumber(row.dataset.entryPrice);
      const savedItem = savedHistoryById.get(row.dataset.historyId);
      const current = optionalNumber(payload.prices?.[symbol]?.mid)
        ?? optionalNumber(savedItem?.outcome?.current)
        ?? optionalNumber(item?.outcome?.current);
      const currentEl = row.querySelector(".history-current");
      const changeEl = row.querySelector(".history-change");
      const exitEl = row.querySelector(".history-exit");
      currentEl.textContent = formatCurrency(current);
      if (entryPrice && current !== null) {
        const change = (Number(current) - entryPrice) / entryPrice;
        changeEl.textContent = formatPercent(change);
        changeEl.classList.toggle("positive", change >= 0);
        changeEl.classList.toggle("negative", change < 0);
        const exitPlan = gexSellAdvisory(item);
        exitEl.textContent = exitPlan.label;
        exitEl.classList.toggle("positive", exitPlan.className === "positive");
        exitEl.classList.toggle("negative", exitPlan.className === "negative");
      } else {
        changeEl.textContent = "n/a";
        changeEl.classList.remove("positive", "negative");
        const exitPlan = gexSellAdvisory(item);
        exitEl.textContent = exitPlan.label;
        exitEl.classList.toggle("positive", exitPlan.className === "positive");
        exitEl.classList.toggle("negative", exitPlan.className === "negative");
      }
    }
  } catch (error) {
    for (const row of fields.tradeHistory.querySelectorAll(".trade-history-row")) {
      const currentEl = row.querySelector(".history-current");
      const changeEl = row.querySelector(".history-change");
      const exitEl = row.querySelector(".history-exit");
      currentEl.textContent = "n/a";
      changeEl.textContent = "n/a";
      exitEl.textContent = "Use plan";
    }
  }
}

function refreshVisibleTradeHistoryPrices() {
  if (!fields.tradeHistory || fields.tradeHistory.querySelectorAll(".trade-history-row").length === 0) {
    return;
  }
  const selectedDate = replayDate.value;
  // Historical rows get their as-of price and high from the same cached
  // one-minute outcome series. A live snapshot here would overwrite that
  // replay point with a later or end-of-day price.
  if (selectedDate && selectedDate !== currentHostDate()) {
    return;
  }
  const selectedTickers = getSelectedTickers();
  const history = loadTradeHistory().filter((item) =>
    historyItemDate(item) === selectedDate && matchesTickerFilter(item, selectedTickers)
  );
  if (history.length === 0) {
    return;
  }
  updateTradeHistoryPrices(history);
}

function sellPlanText(entryPrice) {
  return optionalNumber(entryPrice)
    ? "Exit plan: sell after two consecutive adverse GEX, zero-gamma, or VWAP readings. High and low remain recorded for review."
    : "Tracking begins after a valid entry price is recorded.";
}

function gexSellAdvisory(trade) {
  if (trade?.status === "closed") {
    return { label: trade.exitReason || "Sold by bot", className: paperTradePnl(trade) >= 0 ? "positive" : "negative" };
  }
  const decision = gexSellDecision(trade);
  if (!decision.shouldExit) {
    return decision;
  }
  if (trade?.exitSignalCount === undefined) {
    return decision;
  }
  const count = trade?.exitSignalKey === decision.key ? Number(trade.exitSignalCount || 0) : 0;
  return {
    label: `${decision.label} (${Math.min(count, EXIT_CONFIRMATION_REFRESHES)}/${EXIT_CONFIRMATION_REFRESHES})`,
    className: "negative",
  };
}

function gexSellDecision(trade) {
  const ticker = String(trade?.ticker || trade?.underlying || contractUnderlying(trade || {})).toUpperCase();
  const analysis = latestAnalysisByTicker.get(ticker) || (
    String(lastAnalysis?.ticker || "").toUpperCase() === ticker ? lastAnalysis : null
  );
  if (!analysis) {
    return { shouldExit: false, key: null, label: "Waiting for GEX", className: "" };
  }

  const side = String(trade?.side || trade?.contractType || "").toLowerCase();
  const bias = String(analysis.bias || "neutral").toLowerCase();
  const permission = String(analysis.trade_permission || "").toLowerCase();
  const spot = optionalNumber(analysis.spot);
  const zeroGamma = optionalNumber(analysis.zero_gamma);
  const biasFlipped = (
    side === "call" && bias.includes("bearish")
  ) || (
    side === "put" && bias.includes("bullish")
  );
  if (biasFlipped) {
    return { shouldExit: true, key: `bias:${bias}`, label: `Sell: GEX flipped ${bias}`, className: "negative" };
  }
  if (permission && !permission.includes("possible trade")) {
    return { shouldExit: true, key: "permission", label: "Sell: trade permission disappeared", className: "negative" };
  }
  if (spot !== null && zeroGamma !== null) {
    if (side === "call" && spot < zeroGamma) {
      return { shouldExit: true, key: "zero-gamma", label: "Sell: spot fell below zero gamma", className: "negative" };
    }
    if (side === "put" && spot > zeroGamma) {
      return { shouldExit: true, key: "zero-gamma", label: "Sell: spot rose above zero gamma", className: "negative" };
    }
  }
  const technicals = analysis.technicals || {};
  const technicalPrice = optionalNumber(technicals.last_price);
  const vwap = optionalNumber(technicals.vwap);
  if (technicalPrice !== null && vwap !== null) {
    if (side === "call" && technicalPrice < vwap) {
      return { shouldExit: true, key: "vwap", label: "Sell: underlying fell below VWAP", className: "negative" };
    }
    if (side === "put" && technicalPrice > vwap) {
      return { shouldExit: true, key: "vwap", label: "Sell: underlying rose above VWAP", className: "negative" };
    }
  }
  return { shouldExit: false, key: null, label: "Hold: GEX and VWAP aligned", className: "positive" };
}

function historyItemDate(item) {
  if (item.replayDate) {
    return item.replayDate;
  }
  if (item.timestamp && item.timestamp.day) {
    return item.timestamp.day;
  }
  if (item.timestamp && item.timestamp.iso) {
    return String(item.timestamp.iso).slice(0, 10);
  }
  return "";
}

function loadTradeHistory() {
  try {
    const raw = localStorage.getItem(TRADE_HISTORY_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    return [];
  }
}

function saveTradeHistory(history) {
  const attempts = [
    history,
    compactTradeHistoryForStorage(history, MAX_TRADE_HISTORY_ITEMS),
    compactTradeHistoryForStorage(history, COMPACT_TRADE_HISTORY_ITEMS),
    compactTradeHistoryForStorage(history, Math.floor(COMPACT_TRADE_HISTORY_ITEMS / 2)),
  ];
  try {
    localStorage.setItem(TRADE_HISTORY_STORAGE_KEY, JSON.stringify(attempts[0]));
    schedulePersistentStorageSync();
    return true;
  } catch (_error) {
    for (const compacted of attempts.slice(1)) {
      try {
        localStorage.setItem(TRADE_HISTORY_STORAGE_KEY, JSON.stringify(compacted));
        schedulePersistentStorageSync();
        setStatus(
          `Trade history storage was full, so the app compacted older saved picks to keep the latest ${compacted.length}.`,
          true
        );
        return true;
      } catch (_ignoredError) {
        // Try a smaller save below.
      }
    }
    setStatus("Trade history could not be saved in this browser. Download or clear older history to free space.", true);
    return false;
  }
}

function compactTradeHistoryForStorage(history, limit) {
  return (history || []).slice(0, limit).map((item) => {
    const compact = {
      id: item.id,
      timestamp: item.timestamp,
      replayDate: item.replayDate,
      mode: item.mode,
      rank: item.rank,
      ticker: item.ticker,
      underlying: item.underlying,
      bias: item.bias,
      permission: item.permission,
      contract: item.contract,
      symbol: item.symbol,
      side: item.side,
      expirationDate: item.expirationDate,
      strikePrice: item.strikePrice,
      contractType: item.contractType,
      entryPrice: item.entryPrice,
      entrySpot: item.entrySpot,
      entryGreeks: item.entryGreeks,
      priceLabel: item.priceLabel,
      score: item.score,
      sellPlan: item.sellPlan,
      outcome: compactOutcome(item.outcome),
      decisionSnapshot: compactDecisionSnapshot(item.decisionSnapshot),
    };
    return compact;
  });
}

function compactOutcome(outcome) {
  if (!outcome) {
    return outcome;
  }
  return {
    high: outcome.high,
    high_time: outcome.high_time,
    high_greeks: outcome.high_greeks,
    went_up: outcome.went_up,
    current: outcome.current,
    current_time: outcome.current_time,
    current_age_seconds: outcome.current_age_seconds,
    current_is_stale: outcome.current_is_stale,
    source: outcome.source,
    error: outcome.error,
  };
}

function compactDecisionSnapshot(snapshot) {
  if (!snapshot) {
    return snapshot;
  }
  return {
    timestamp: snapshot.timestamp,
    gex: snapshot.gex,
    technicals: snapshot.technicals
      ? {
          lastPrice: snapshot.technicals.lastPrice,
          vwap: snapshot.technicals.vwap,
          sma50: snapshot.technicals.sma50,
          sma200: snapshot.technicals.sma200,
          scoreAdjustment: snapshot.technicals.scoreAdjustment,
        }
      : null,
    contract: snapshot.contract,
  };
}

function loadPaperLedger() {
  try {
    const raw = localStorage.getItem(PAPER_LEDGER_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) {
      return [];
    }
    const normalized = parsed.map(normalizePaperLedgerTrade);
    const unique = uniquePaperLedgerTrades(normalized);
    if (JSON.stringify(unique) !== JSON.stringify(parsed)) {
      localStorage.setItem(PAPER_LEDGER_STORAGE_KEY, JSON.stringify(unique));
    }
    return unique;
  } catch (_error) {
    return [];
  }
}

function normalizePaperLedgerTrade(trade) {
  const { targetPrice: _targetPrice, stopPrice: _stopPrice, ...withoutPercentageRules } = trade || {};
  const entry = optionalNumber(withoutPercentageRules.entryPrice);
  const current = optionalNumber(withoutPercentageRules.currentPrice)
    ?? optionalNumber(withoutPercentageRules.exitPrice)
    ?? entry;
  const observed = [
    entry,
    current,
    optionalNumber(withoutPercentageRules.highPrice),
    optionalNumber(withoutPercentageRules.lowPrice),
  ].filter((value) => value !== null && Number.isFinite(value));
  const legacyPercentageExit = ["Take profit +30%", "Stop loss -30%"].includes(withoutPercentageRules.exitReason);
  const normalized = {
    ...withoutPercentageRules,
    status: legacyPercentageExit ? "open" : withoutPercentageRules.status || "open",
    currentPrice: current,
    highPrice: observed.length ? Math.max(...observed) : null,
    lowPrice: observed.length ? Math.min(...observed) : null,
  };
  if (legacyPercentageExit) {
    delete normalized.exitPrice;
    delete normalized.exitReason;
    delete normalized.exitTimestamp;
  }
  return normalized;
}

function savePaperLedger(ledger) {
  try {
    localStorage.setItem(PAPER_LEDGER_STORAGE_KEY, JSON.stringify(uniquePaperLedgerTrades(ledger)));
    schedulePersistentStorageSync();
  } catch (_error) {
    if (fields.paperLedgerOpen) {
      fields.paperLedgerOpen.textContent = "Paper simulation ledger could not be saved in this browser.";
    }
  }
}

async function initializePersistentStorage() {
  persistentStorageHydrating = true;
  try {
    const snapshot = await getJson("/api/storage/snapshot");
    const browserHistory = loadTradeHistory();
    const databaseHistory = Array.isArray(snapshot.trade_history) ? snapshot.trade_history : [];
    const mergedHistory = mergePersistentRecords(databaseHistory, browserHistory, tradeHistoryMergeKey)
      .sort((a, b) => String(b.timestamp?.iso || "").localeCompare(String(a.timestamp?.iso || "")));
    persistTradeHistoryLocally(mergedHistory);

    const browserLedger = loadPaperLedger();
    const databaseLedger = Array.isArray(snapshot.paper_ledger) ? snapshot.paper_ledger : [];
    const mergedLedger = uniquePaperLedgerTrades(
      mergePersistentRecords(databaseLedger, browserLedger, paperLedgerMergeKey)
    );
    persistPaperLedgerLocally(mergedLedger);

    const mergedTracking = mergeTrackedTickerHistory(
      snapshot.tracked_tickers,
      loadTrackedTickerHistory()
    );
    localStorage.setItem(TRACKING_HISTORY_STORAGE_KEY, JSON.stringify(mergedTracking));
    localStorage.setItem(DATABASE_MIGRATION_STORAGE_KEY, "1");
    renderTradeHistory();
    renderPaperLedger();
    renderTrackingOverview();
  } catch (error) {
    console.warn("SQLite storage is unavailable; browser storage remains active.", error);
  } finally {
    persistentStorageHydrating = false;
    schedulePersistentStorageSync({ immediate: true });
  }
}

function mergePersistentRecords(databaseRows, browserRows, keyFor) {
  const merged = new Map();
  for (const row of [...(databaseRows || []), ...(browserRows || [])]) {
    if (!row || typeof row !== "object") {
      continue;
    }
    merged.set(keyFor(row), row);
  }
  return [...merged.values()];
}

function tradeHistoryMergeKey(item) {
  return String(item.id || [
    historyItemDate(item),
    item.timestamp?.iso,
    item.symbol,
    item.rank,
  ].join(":"));
}

function paperLedgerMergeKey(trade) {
  return String(trade.id || [paperLedgerDay(trade), trade.symbol].join(":"));
}

function mergeTrackedTickerHistory(databaseTracking, browserTracking) {
  const merged = {};
  for (const source of [databaseTracking, browserTracking]) {
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      continue;
    }
    for (const [day, tickers] of Object.entries(source)) {
      const values = Array.isArray(tickers) ? tickers : [];
      merged[day] = [...new Set([...(merged[day] || []), ...values]
        .map((ticker) => String(ticker).trim().toUpperCase())
        .filter(Boolean))].sort();
    }
  }
  return merged;
}

function persistTradeHistoryLocally(history) {
  const attempts = [
    history,
    compactTradeHistoryForStorage(history, MAX_TRADE_HISTORY_ITEMS),
    compactTradeHistoryForStorage(history, COMPACT_TRADE_HISTORY_ITEMS),
  ];
  for (const rows of attempts) {
    try {
      localStorage.setItem(TRADE_HISTORY_STORAGE_KEY, JSON.stringify(rows));
      return true;
    } catch (_error) {
      // SQLite still retains all rows if the browser cache is full.
    }
  }
  return false;
}

function persistPaperLedgerLocally(ledger) {
  try {
    localStorage.setItem(PAPER_LEDGER_STORAGE_KEY, JSON.stringify(uniquePaperLedgerTrades(ledger)));
    return true;
  } catch (_error) {
    return false;
  }
}

function schedulePersistentStorageSync({ immediate = false } = {}) {
  if (persistentStorageHydrating) {
    return;
  }
  if (persistentStorageSyncTimer !== null) {
    clearTimeout(persistentStorageSyncTimer);
  }
  persistentStorageSyncTimer = setTimeout(syncPersistentStorage, immediate ? 0 : 350);
}

async function syncPersistentStorage() {
  persistentStorageSyncTimer = null;
  if (persistentStorageSyncInFlight) {
    persistentStorageSyncQueued = true;
    return;
  }
  persistentStorageSyncInFlight = true;
  try {
    await postJson("/api/storage/sync", {
      trade_history: loadTradeHistory(),
      paper_ledger: loadPaperLedger(),
      tracked_tickers: loadTrackedTickerHistory(),
    });
  } catch (error) {
    console.warn("SQLite sync failed; records remain cached in this browser.", error);
  } finally {
    persistentStorageSyncInFlight = false;
    if (persistentStorageSyncQueued) {
      persistentStorageSyncQueued = false;
      schedulePersistentStorageSync({ immediate: true });
    }
  }
}

async function deletePersistentStorageDay(recordType, day) {
  try {
    await postJson("/api/storage/delete-day", {
      record_type: recordType,
      day,
    });
  } catch (error) {
    console.warn(`Could not clear ${recordType} from SQLite.`, error);
  }
}

function uniquePaperLedgerTrades(ledger) {
  const seen = new Set();
  return [...ledger]
    .sort((a, b) => String(a.timestamp?.iso || "").localeCompare(String(b.timestamp?.iso || "")))
    .filter((trade) => {
      const day = paperLedgerDay(trade);
      const symbol = String(trade.symbol || "").toUpperCase();
      const key = day && symbol ? `${day}:${symbol}` : String(trade.id || "");
      if (!key || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    })
    .sort((a, b) => String(b.timestamp?.iso || "").localeCompare(String(a.timestamp?.iso || "")));
}

function contractTitleMarkup(candidate) {
  const side = contractSide(candidate);
  return `
    <span class="contract-title">
      <strong>${readableContractName(candidate)}</strong>
      <em>${candidate.symbol}</em>
      <b class="contract-badge ${side}">${side.toUpperCase()}</b>
    </span>
  `;
}

function contractMetric(label, value, description) {
  return `
    <span class="contract-metric">
      <i>${label}<b class="info-dot" data-tooltip="${escapeAttribute(description)}" aria-label="${escapeAttribute(description)}" tabindex="0">i</b></i>
      <strong>${value}</strong>
    </span>
  `;
}

function optionSparklineMarkup(candidate) {
  const path = sparklinePath(candidate.price_path || []);
  const first = firstFinite(candidate.price_path || []);
  const last = lastFinite(candidate.price_path || []);
  const trendClass = first !== null && last !== null && last >= first ? "spark-up" : "spark-down";
  const label = path
    ? `Day path ${formatCurrency(first)} to ${formatCurrency(last)}`
    : "No intraday option bars yet";

  if (!path) {
    return `
      <span class="option-sparkline spark-empty" aria-label="${label}">
        <em>No chart</em>
      </span>
    `;
  }

  return `
    <span class="option-sparkline ${trendClass}" aria-label="${label}">
      <svg viewBox="0 0 160 46" role="img" focusable="false">
        <path class="spark-area" d="${path.area}"></path>
        <path class="spark-line" d="${path.line}"></path>
      </svg>
      <em>${formatCurrency(first)} -> ${formatCurrency(last)}</em>
    </span>
  `;
}

function sparklinePath(values) {
  const points = (values || []).map(Number).filter(Number.isFinite);
  if (points.length < 2) {
    return null;
  }

  const width = 160;
  const height = 46;
  const pad = 4;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const coordinates = points.map((value, index) => {
    const x = pad + (index / (points.length - 1)) * (width - pad * 2);
    const y = height - pad - ((value - min) / range) * (height - pad * 2);
    return [Number(x.toFixed(2)), Number(y.toFixed(2))];
  });
  const line = coordinates.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
  const area = `${line} L ${coordinates[coordinates.length - 1][0]} ${height - pad} L ${coordinates[0][0]} ${height - pad} Z`;
  return { line, area };
}

function firstFinite(values) {
  for (const value of values || []) {
    const number = Number(value);
    if (Number.isFinite(number)) {
      return number;
    }
  }
  return null;
}

function lastFinite(values) {
  for (let index = (values || []).length - 1; index >= 0; index -= 1) {
    const number = Number(values[index]);
    if (Number.isFinite(number)) {
      return number;
    }
  }
  return null;
}

function showMetricTooltip(target) {
  const message = target.dataset.tooltip;
  if (!message) {
    return;
  }
  metricTooltip.textContent = message;
  metricTooltip.classList.add("visible");

  const rect = target.getBoundingClientRect();
  const tooltipRect = metricTooltip.getBoundingClientRect();
  const margin = 10;
  let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
  left = Math.max(margin, Math.min(left, window.innerWidth - tooltipRect.width - margin));

  let top = rect.bottom + 8;
  if (top + tooltipRect.height + margin > window.innerHeight) {
    top = rect.top - tooltipRect.height - 8;
  }
  metricTooltip.style.left = `${left}px`;
  metricTooltip.style.top = `${Math.max(margin, top)}px`;
}

function hideMetricTooltip() {
  metricTooltip.classList.remove("visible");
}

function readableContractName(candidate) {
  const underlying = contractUnderlying(candidate);
  const expiration = formatContractDate(candidate.expiration_date);
  const strike = formatStrike(candidate.strike_price);
  const side = contractSide(candidate);
  return `${underlying} Exp ${expiration} ${strike} ${capitalize(side)}`;
}

function contractUnderlying(candidate) {
  if (candidate.underlying_symbol) {
    return String(candidate.underlying_symbol).toUpperCase();
  }
  const match = String(candidate.symbol || "").match(/^([A-Z]+)\d{6}[CP]\d{8}$/);
  return match ? match[1] : String(candidate.symbol || "").replace(/\d.*$/, "").toUpperCase();
}

function contractSide(candidate) {
  const type = String(candidate.contract_type || "").toLowerCase();
  if (type === "put" || type === "call") {
    return type;
  }
  const match = String(candidate.symbol || "").match(/^[A-Z]+\d{6}([CP])\d{8}$/);
  return match && match[1] === "P" ? "put" : "call";
}

function formatContractDate(value) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value || "-";
  }
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDisplayTime(value) {
  const parts = String(value || "").split(":");
  if (parts.length < 2) {
    return value || "-";
  }
  const date = new Date();
  date.setHours(Number(parts[0]), Number(parts[1]), Number(parts[2] || 0), 0);
  return date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatHistoryDate(date) {
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatStrike(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: Number.isInteger(Number(value)) ? 0 : 2,
    maximumFractionDigits: 2,
  });
}

function capitalize(value) {
  return value ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : "";
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttribute(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function getJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

async function getJsonWithTimeout(url, { signal, timeoutMs }) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const abortFromParent = () => controller.abort();

  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", abortFromParent, { once: true });
    }
  }

  try {
    const response = await fetch(url, { signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Request failed.");
    }
    return payload;
  } finally {
    clearTimeout(timeout);
    if (signal) {
      signal.removeEventListener("abort", abortFromParent);
    }
  }
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

function optionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return Number(value);
}

function formatCurrency(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return Number(value).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function formatOptionPriceAndCost(value) {
  const price = optionalNumber(value);
  if (price === null) {
    return "-";
  }
  return `${formatCurrency(price)} / ${formatCurrency(price * OPTION_CONTRACT_MULTIPLIER)}`;
}

function formatSignedCurrency(value) {
  const number = Number(value || 0);
  const formatted = formatCurrency(Math.abs(number));
  return `${number > 0 ? "+" : number < 0 ? "-" : ""}${formatted}`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return Number(value).toLocaleString(undefined, {
    style: "percent",
    maximumFractionDigits: 1,
  });
}

function formatGreek(label, value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return `${label}: n/a`;
  }
  return `${label}: ${formatGreekValue(label, value)}`;
}

function formatGreekValue(label, value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "n/a";
  }
  if (label === "iv") {
    return formatPercent(value);
  }
  if (label === "gamma") {
    const absolute = Math.abs(Number(value));
    return Number(value).toFixed(absolute > 0 && absolute < 0.001 ? 6 : 4);
  }
  return Number(value).toFixed(3);
}

function greekSummary(candidate) {
  const suffix = candidate.greeks_estimated ? " estimated" : "";
  return `${formatGreek("delta", candidate.delta)} ${formatGreek("gamma", candidate.gamma)} ${formatGreek("iv", candidate.implied_volatility)}${suffix}`;
}

function setAlpacaStatus(message, isError) {
  if (!alpacaStatus) {
    setStatus(message, isError);
    return;
  }
  alpacaStatus.textContent = message;
  alpacaStatus.classList.toggle("error", isError);
}


function setStatus(message, isError) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
