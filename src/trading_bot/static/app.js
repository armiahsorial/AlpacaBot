const form = document.querySelector("#analysis-form");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const button = document.querySelector("#analyze-button");
const autoRefresh = document.querySelector("#auto-refresh");
const refreshSeconds = document.querySelector("#refresh-seconds");
const alpacaStatus = document.querySelector("#alpaca-status");
const refreshAlpacaButton = document.querySelector("#refresh-alpaca");
const refreshPositionsButton = document.querySelector("#refresh-positions");
const paperOrderForm = document.querySelector("#paper-order-form");
const loadBarButton = document.querySelector("#load-bar");
const loadContractsButton = document.querySelector("#load-contracts");
const replayDate = document.querySelector("#replay-date");
const replayTime = document.querySelector("#replay-time");
const replayClock = document.querySelector("#replay-clock");
const replayPlay = document.querySelector("#replay-play");
const replayRefresh = document.querySelector("#replay-refresh");
const replayToday = document.querySelector("#replay-today");
const stageBestPickButton = document.querySelector("#stage-best-pick");
const clearTradeHistoryButton = document.querySelector("#clear-trade-history");
const speedButtons = document.querySelectorAll("[data-speed]");
const barSymbol = document.querySelector("#bar-symbol");
const latestBar = document.querySelector("#latest-bar");
const metricTooltip = document.createElement("div");
metricTooltip.className = "metric-tooltip";
metricTooltip.setAttribute("role", "tooltip");
document.body.appendChild(metricTooltip);
let refreshTimer = null;
let replayTimer = null;
let replaySpeed = 1;
let lastAnalysis = null;
let isAnalysisRunning = false;
let isInspectingContract = false;
let isReplayLoading = false;
let replayAbortController = null;
let lastReplayFetchSecond = null;
let lastReplayFetchStartedAt = 0;
let currentBestPick = null;
const REPLAY_FETCH_STEP_SECONDS = 300;
const REPLAY_MIN_FETCH_INTERVAL_MS = 5000;
const TRADE_HISTORY_STORAGE_KEY = "tradingBot.tradePermissionHistory";
const MAX_TRADE_HISTORY_ITEMS = 100;
const PACIFIC_TO_EASTERN_SECONDS = 3 * 60 * 60;

const fields = {
  tradePermission: document.querySelector("#trade-permission"),
  bias: document.querySelector("#bias"),
  confidence: document.querySelector("#confidence"),
  score: document.querySelector("#score"),
  spot: document.querySelector("#spot"),
  zeroGamma: document.querySelector("#zero-gamma"),
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
  tradeHistory: document.querySelector("#trade-history"),
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runAnalysis();
  scheduleRefresh();
});

form.addEventListener("change", () => {
  runAnalysis();
  scheduleRefresh();
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

refreshAlpacaButton.addEventListener("click", () => {
  refreshAlpaca();
});

refreshPositionsButton.addEventListener("click", () => {
  loadPositions();
});

loadBarButton.addEventListener("click", () => {
  loadLatestBar();
});

loadContractsButton.addEventListener("click", () => {
  isInspectingContract = false;
  loadOptionReplay();
});

replayDate.addEventListener("change", () => {
  renderTradeHistory();
  loadOptionReplay();
});

replayTime.addEventListener("input", () => {
  updateReplayClock();
});

replayTime.addEventListener("change", () => {
  loadOptionReplay();
});

replayPlay.addEventListener("click", () => {
  toggleReplay();
});

replayRefresh.addEventListener("click", () => {
  loadOptionReplay({ force: true });
});

replayToday.addEventListener("click", () => {
  jumpToTodayNow();
});

stageBestPickButton.addEventListener("click", () => {
  if (!currentBestPick) {
    return;
  }
  stageCandidate(currentBestPick.candidate, currentBestPick.entryPrice, currentBestPick.message);
});

clearTradeHistoryButton.addEventListener("click", () => {
  saveTradeHistory([]);
  renderTradeHistory();
});

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

paperOrderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitPaperOrder();
});

async function runAnalysis({ isRefresh = false } = {}) {
  if (isAnalysisRunning) {
    return;
  }

  if (isRefresh && (isInspectingContract || replayTimer !== null)) {
    setStatus("Auto-refresh paused while you inspect contracts.", false);
    return;
  }

  isAnalysisRunning = true;
  const { ticker, period } = getFormValues();

  setStatus(isRefresh ? "Refreshing GEX data..." : "Pulling GEX data...", false);
  if (button) {
    button.disabled = true;
  }

  try {
    const query = new URLSearchParams(getFormValues());
    const response = await fetch(`/api/analyze?${query.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Analysis failed.");
    }
    lastAnalysis = payload;
    renderAnalysis(payload);
    if (!isRefresh && !isInspectingContract) {
      await loadOptionRecommendation();
    }
    setStatus(`Updated ${ticker} ${period} at ${new Date().toLocaleTimeString()}.`, false);
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

function getFormValues() {
  const data = new FormData(form);
  return {
    ticker: String(data.get("ticker") || "NDX").trim().toUpperCase(),
    period: String(data.get("period") || "zero"),
  };
}

function scheduleRefresh() {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }

  if (!autoRefresh.checked) {
    return;
  }

  const seconds = Number(refreshSeconds.value || 1);
  refreshTimer = setInterval(() => {
    runAnalysis({ isRefresh: true });
  }, seconds * 1000);
}

runAnalysis();
scheduleRefresh();
refreshAlpaca();
initializeReplayControls();
renderTradeHistory();

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
  await Promise.all([loadAccount(), loadPositions()]);
}

async function loadAccount() {
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

async function loadOptionRecommendation() {
  const { ticker, period } = getFormValues();
  fields.contractSummary.textContent = "Scanning Alpaca options...";
  fields.contractSummary.classList.remove("error");
  fields.contractList.textContent = "-";
  resetBestPick();

  try {
    const query = new URLSearchParams({
      ticker,
      period,
      max_expiration_days: "14",
      limit: "5",
    });
    const payload = await getJson(`/api/options/recommend?${query.toString()}`);
    renderOptionRecommendation(payload);
  } catch (error) {
    fields.contractSummary.textContent = error.message;
    fields.contractSummary.classList.add("error");
    resetBestPick();
  }
}

async function loadOptionReplay({ force = false } = {}) {
  if (isReplayLoading) {
    if (replayAbortController) {
      replayAbortController.abort();
    }
    fields.contractSummary.textContent = "Canceling previous replay request...";
  }

  isReplayLoading = true;
  replayAbortController = new AbortController();
  isInspectingContract = true;
  autoRefresh.checked = false;
  scheduleRefresh();
  const { ticker, period } = getFormValues();
  updateReplayClock();
  const replaySecond = Number(replayTime.value || 57540);
  const now = Date.now();
  if (
    !force &&
    lastReplayFetchSecond !== null &&
    Math.abs(replaySecond - lastReplayFetchSecond) < REPLAY_FETCH_STEP_SECONDS
  ) {
    isReplayLoading = false;
    replayAbortController = null;
    fields.contractSummary.textContent = `Clock updated to ${replayClock.textContent} PT. Press Update Data to rescore this exact second.`;
    return;
  }
  if (!force && now - lastReplayFetchStartedAt < REPLAY_MIN_FETCH_INTERVAL_MS) {
    isReplayLoading = false;
    replayAbortController = null;
    return;
  }
  lastReplayFetchStartedAt = now;

  fields.contractSummary.textContent =
    "Loading historical GEX and Alpaca option bars. First load for a ticker/date can take a minute or two...";
  fields.contractSummary.classList.remove("error");
  fields.contractList.textContent = "-";
  resetBestPick();

  try {
    const query = new URLSearchParams({
      ticker,
      period,
      date: replayDate.value,
      time: getReplayMarketClock(),
      max_expiration_days: "14",
      limit: "5",
    });
    const payload = await getJsonWithTimeout(`/api/options/replay?${query.toString()}`, {
      signal: replayAbortController.signal,
      timeoutMs: 90000,
    });
    lastReplayFetchSecond = replaySecond;
    renderOptionReplay(payload);
  } catch (error) {
    if (error.name === "AbortError") {
      fields.contractSummary.textContent = "Previous replay request canceled. Press Scan to try again.";
    } else {
      fields.contractSummary.textContent = error.message;
      fields.contractSummary.classList.add("error");
      resetBestPick();
    }
  } finally {
    isReplayLoading = false;
    replayAbortController = null;
  }
}

function renderOptionReplay(payload) {
  const recommendation = payload.recommendation || {};
  const warning = payload.warning ? ` ${payload.warning}` : "";
  const gexTime = recommendation.gex_timestamp ? ` GEX ${new Date(recommendation.gex_timestamp * 1000).toLocaleTimeString()}.` : "";
  if (payload.analysis) {
    lastAnalysis = payload.analysis;
    renderAnalysis(payload.analysis);
    setStatus(`Replay GEX map updated for ${payload.date} ${replayClock.textContent} Pacific time.`, false);
  }
  fields.contractSummary.classList.toggle("error", Boolean(payload.warning));
  fields.contractSummary.textContent = `${payload.date} ${replayClock.textContent} PT: ${recommendation.recommendation || "No recommendation."}${gexTime}${warning}`;
  renderBestPick(payload, "replay");

  if (!payload.candidates || payload.candidates.length === 0) {
    fields.contractList.textContent = "No replay bars found for this time.";
    return;
  }

  fields.contractList.innerHTML = "";
  for (const candidate of payload.candidates) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `contract-row contract-${contractSide(candidate)}`;
    row.innerHTML = `
      ${contractTitleMarkup(candidate)}
      ${contractMetric("Price", formatCurrency(candidate.close), "What this option was worth at the selected replay time. This is the old market price, not today's price.")}
      ${contractMetric("Day", formatPercent(candidate.day_change_pct), "How much this option had moved that day by the selected replay time. Positive means it was up; negative means it was down.")}
      ${contractMetric("Volume", formatNumber(candidate.volume || 0), "How many of this exact option traded in the latest 1-minute bar. Thin liquidity: 1-10 contracts. Healthier/thicker activity: hundreds or thousands in a minute.")}
      ${contractMetric("Replay score", formatNumber(candidate.replay_score), "The bot's replay rank. It starts with the contract quality score, then adds what happened to price and volume during that historical day. Higher means it ranked better.")}
      <small>${formatGreek("delta", candidate.delta)} ${formatGreek("gamma", candidate.gamma)} ${formatGreek("iv", candidate.implied_volatility)}</small>
    `;
    row.addEventListener("click", () => {
      isInspectingContract = true;
      autoRefresh.checked = false;
      scheduleRefresh();
      stageCandidate(candidate, candidate.close, `Staged ${candidate.symbol} from replay at ${replayClock.textContent} PT.`);
    });
    fields.contractList.appendChild(row);
  }
}

function initializeReplayControls() {
  const today = new Date(`${currentPacificDate()}T12:00:00`);
  const priorDay = new Date(today);
  priorDay.setDate(today.getDate() - 1);
  while (priorDay.getDay() === 0 || priorDay.getDay() === 6) {
    priorDay.setDate(priorDay.getDate() - 1);
  }
  replayDate.value = formatDateInput(priorDay);
  updateReplayClock();
  for (const button of speedButtons) {
    button.classList.toggle("active", Number(button.dataset.speed) === replaySpeed);
  }
}

function currentPacificDate() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (type) => parts.find((item) => item.type === type)?.value || "01";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function updateReplayClock() {
  const seconds = Number(replayTime.value || 46740);
  replayClock.textContent = formatClock(seconds);
}

function getReplayMarketClock() {
  return formatClock(Number(replayTime.value || 46740) + PACIFIC_TO_EASTERN_SECONDS);
}

async function jumpToTodayNow() {
  const now = new Date();
  const pacificParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(now);
  const part = (type) => pacificParts.find((item) => item.type === type)?.value || "00";
  const marketDate = `${part("year")}-${part("month")}-${part("day")}`;
  const pacificSeconds = Number(part("hour")) * 3600 + Number(part("minute")) * 60 + Number(part("second"));
  const min = Number(replayTime.min);
  const max = Number(replayTime.max);
  const clampedSeconds = Math.min(Math.max(pacificSeconds, min), max);

  replayDate.value = marketDate;
  replayTime.value = String(clampedSeconds);
  lastReplayFetchSecond = null;
  updateReplayClock();
  renderTradeHistory();

  const isMarketHours = pacificSeconds >= min && pacificSeconds <= max;
  if (isMarketHours) {
    isInspectingContract = false;
    await runAnalysis();
    setStatus(`Live view updated to today at ${replayClock.textContent} Pacific time.`, false);
    return;
  }

  setStatus(`Market is outside regular hours. Showing nearest replay point for ${marketDate} ${replayClock.textContent} Pacific time.`, false);
  await loadOptionReplay({ force: true });
}

function toggleReplay() {
  if (replayTimer !== null) {
    clearInterval(replayTimer);
    replayTimer = null;
    replayPlay.textContent = "Play";
    return;
  }

  isInspectingContract = true;
  autoRefresh.checked = false;
  scheduleRefresh();
  replayPlay.textContent = "Pause";
  replayTimer = setInterval(() => {
    if (isReplayLoading) {
      const nextValue = Math.min(Number(replayTime.value) + replaySpeed, Number(replayTime.max));
      replayTime.value = String(nextValue);
      updateReplayClock();
      return;
    }
    const previousValue = Number(replayTime.value);
    const nextValue = Math.min(previousValue + replaySpeed, Number(replayTime.max));
    replayTime.value = String(nextValue);
    updateReplayClock();
    if (Math.floor(previousValue / REPLAY_FETCH_STEP_SECONDS) !== Math.floor(nextValue / REPLAY_FETCH_STEP_SECONDS)) {
      loadOptionReplay();
    }
    if (nextValue >= Number(replayTime.max)) {
      toggleReplay();
    }
  }, 1000);
}

function formatClock(totalSeconds) {
  const hour = Math.floor(totalSeconds / 3600);
  const minute = Math.floor((totalSeconds % 3600) / 60);
  const second = totalSeconds % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}`;
}

function renderOptionRecommendation(payload) {
  fields.contractSummary.classList.toggle("error", payload.trade_permission === "no trade");
  fields.contractSummary.textContent = `${payload.bias} ${payload.contract_type || ""} read: ${payload.recommendation}`;

  if (payload.warnings && payload.warnings.length > 0) {
    fields.contractSummary.textContent += ` ${payload.warnings.join(" ")}`;
  }
  renderBestPick(payload, "live");

  if (!payload.candidates || payload.candidates.length === 0) {
    fields.contractList.textContent = "No contract candidates.";
    return;
  }

  fields.contractList.innerHTML = "";
  for (const candidate of payload.candidates) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `contract-row contract-${contractSide(candidate)}`;
    row.innerHTML = `
      ${contractTitleMarkup(candidate)}
      ${contractMetric("Mid", formatCurrency(candidate.mid), "The middle between what buyers are bidding and sellers are asking. Think of it as a fair reference price, not a guaranteed fill.")}
      ${contractMetric("Spread", formatPercent(candidate.spread_pct), "The gap between buy and sell prices. Smaller is usually better because it may cost less to enter and exit.")}
      ${contractMetric("Open int", candidate.open_interest ?? "n/a", "How many of this option are still open in the market. Bigger usually means more people are involved and the option may be easier to trade.")}
      ${contractMetric("Score", formatNumber(candidate.score), "The bot's quality rank for this contract. It favors options near the GEX target, with tighter pricing and better activity.")}
      <small>${formatGreek("delta", candidate.delta)} ${formatGreek("gamma", candidate.gamma)} ${formatGreek("iv", candidate.implied_volatility)}</small>
    `;
    row.addEventListener("click", () => {
      isInspectingContract = true;
      autoRefresh.checked = false;
      scheduleRefresh();
      stageCandidate(candidate, candidate.mid, `Staged ${candidate.symbol} as a paper limit order.`);
    });
    fields.contractList.appendChild(row);
  }
}

function renderBestPick(payload, mode) {
  const recommendation = mode === "replay" ? payload.recommendation || {} : payload;
  const candidate = (payload.candidates || [])[0];

  if (!candidate) {
    currentBestPick = null;
    fields.bestPick.classList.remove("hidden");
    fields.bestPick.classList.add("best-pick-wait");
    fields.bestPickAction.textContent = "No contract pick";
    fields.bestPickContract.textContent = "No ranked candidate is available for this read.";
    fields.bestPickReason.textContent = payload.warning || "Run a scan after GEX and Alpaca both return usable data.";
    stageBestPickButton.disabled = true;
    return;
  }

  const permission = String(recommendation.trade_permission || "").toLowerCase();
  const bias = String(recommendation.bias || "unknown");
  const score = mode === "replay" ? candidate.replay_score : candidate.score;
  const entryPrice = mode === "replay" ? candidate.close : candidate.mid;
  const priceLabel = mode === "replay" ? "last replay close" : "mid";
  const hasTradePermission = permission.includes("possible trade");
  const isStandDown = !hasTradePermission || Boolean(payload.warning);
  const action = hasTradePermission && !payload.warning ? "Buy candidate after confirmation" : "Wait / watch only";
  const reasonParts = [
    `GEX is ${bias}${permission ? ` with ${permission} permission` : ""}.`,
    `${candidate.symbol} is the top ranked ${candidate.contract_type} with score ${formatNumber(score)}.`,
  ];

  if (entryPrice) {
    reasonParts.push(`Reference ${priceLabel}: ${formatCurrency(entryPrice)}.`);
  }
  if (payload.warning) {
    reasonParts.push(payload.warning);
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
  fields.bestPickContract.textContent = `${readableContractName(candidate)} | ${priceLabel} ${formatCurrency(entryPrice)}`;
  fields.bestPickReason.textContent = reasonParts.join(" ");
  stageBestPickButton.disabled = false;

  if (!isStandDown) {
    recordTradePermissionPick({
      candidate,
      recommendation,
      payload,
      mode,
      entryPrice,
      priceLabel,
      score,
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
  stageBestPickButton.disabled = true;
}

function stageCandidate(candidate, entryPrice, message) {
  paperOrderForm.elements.symbol.value = candidate.symbol;
  paperOrderForm.elements.side.value = "buy";
  paperOrderForm.elements.qty.value = "1";
  paperOrderForm.elements.type.value = "limit";
  paperOrderForm.elements.limit_price.value = entryPrice ? Number(entryPrice).toFixed(2) : "";
  setAlpacaStatus(message, false);
}

function recordTradePermissionPick({ candidate, recommendation, payload, mode, entryPrice, priceLabel, score }) {
  const timestamp = pickTimestamp({ recommendation, payload, mode });
  const item = {
    id: `${mode}:${timestamp.iso}:${candidate.symbol}`,
    timestamp,
    replayDate: mode === "replay" && payload.date ? payload.date : timestamp.day,
    mode,
    ticker: recommendation.ticker || contractUnderlying(candidate),
    bias: recommendation.bias || "unknown",
    permission: recommendation.trade_permission || "trade permission",
    contract: readableContractName(candidate),
    symbol: candidate.symbol,
    side: contractSide(candidate),
    entryPrice,
    priceLabel,
    score,
  };
  const history = loadTradeHistory();
  const withoutDuplicate = history.filter((existing) => existing.id !== item.id);
  saveTradeHistory([item, ...withoutDuplicate].slice(0, MAX_TRADE_HISTORY_ITEMS));
  renderTradeHistory();
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

function renderTradeHistory() {
  const selectedDate = replayDate.value;
  const history = loadTradeHistory().filter((item) => historyItemDate(item) === selectedDate);
  if (history.length === 0) {
    fields.tradeHistory.textContent = selectedDate
      ? `No trade-permission picks recorded for ${formatContractDate(selectedDate)}.`
      : "No trade-permission picks yet.";
    return;
  }
  fields.tradeHistory.innerHTML = "";
  for (const item of history) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `trade-history-row contract-${item.side || "call"}`;
    row.innerHTML = `
      <span>
        <strong>${item.timestamp.label}</strong>
        <em>${item.contract}</em>
      </span>
      <span>${formatCurrency(item.entryPrice)}</span>
      <span>${item.bias}</span>
      <span>${formatOptionalNumber(item.score)}</span>
    `;
    row.addEventListener("click", () => {
      paperOrderForm.elements.symbol.value = item.symbol;
      paperOrderForm.elements.side.value = "buy";
      paperOrderForm.elements.qty.value = "1";
      paperOrderForm.elements.type.value = "limit";
      paperOrderForm.elements.limit_price.value = item.entryPrice ? Number(item.entryPrice).toFixed(2) : "";
      setAlpacaStatus(`Staged ${item.symbol} from trade permission history.`, false);
    });
    fields.tradeHistory.appendChild(row);
  }
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
  try {
    localStorage.setItem(TRADE_HISTORY_STORAGE_KEY, JSON.stringify(history));
  } catch (_error) {
    fields.tradeHistory.textContent = "Trade history could not be saved in this browser.";
  }
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
  if (label === "iv") {
    return `${label}: ${formatPercent(value)}`;
  }
  return `${label}: ${Number(value).toFixed(3)}`;
}

function setAlpacaStatus(message, isError) {
  alpacaStatus.textContent = message;
  alpacaStatus.classList.toggle("error", isError);
}


function setStatus(message, isError) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
