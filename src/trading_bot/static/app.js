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
const speedButtons = document.querySelectorAll("[data-speed]");
const barSymbol = document.querySelector("#bar-symbol");
const latestBar = document.querySelector("#latest-bar");
let refreshTimer = null;
let replayTimer = null;
let replaySpeed = 1;
let lastAnalysis = null;
let isAnalysisRunning = false;
let isInspectingContract = false;
let isReplayLoading = false;
let replayAbortController = null;

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
      loadOptionRecommendation();
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
  }
}

async function loadOptionReplay() {
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
  fields.contractSummary.textContent =
    "Loading historical GEX and Alpaca option bars. First load for a ticker/date can take a minute or two...";
  fields.contractSummary.classList.remove("error");
  fields.contractList.textContent = "-";

  try {
    const validationQuery = new URLSearchParams({
      ticker,
      period,
      date: replayDate.value,
    });
    const validation = await getJsonWithTimeout(`/api/options/replay/validate?${validationQuery.toString()}`, {
      signal: replayAbortController.signal,
      timeoutMs: 20000,
    });
    if (!validation.valid) {
      throw new Error(validation.error || `No GEX replay data found for ${ticker} ${period} on ${replayDate.value}.`);
    }

    const query = new URLSearchParams({
      ticker,
      period,
      date: replayDate.value,
      time: replayClock.textContent,
      max_expiration_days: "14",
      limit: "5",
    });
    const payload = await getJsonWithTimeout(`/api/options/replay?${query.toString()}`, {
      signal: replayAbortController.signal,
      timeoutMs: 90000,
    });
    renderOptionReplay(payload);
  } catch (error) {
    if (error.name === "AbortError") {
      fields.contractSummary.textContent = "Previous replay request canceled. Press Scan to try again.";
    } else {
      fields.contractSummary.textContent = error.message;
      fields.contractSummary.classList.add("error");
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
  fields.contractSummary.classList.toggle("error", Boolean(payload.warning));
  fields.contractSummary.textContent = `${payload.date} ${payload.selected_time}: ${recommendation.recommendation || "No recommendation."}${gexTime}${warning}`;

  if (!payload.candidates || payload.candidates.length === 0) {
    fields.contractList.textContent = "No replay bars found for this time.";
    return;
  }

  fields.contractList.innerHTML = "";
  for (const candidate of payload.candidates) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "contract-row";
    row.innerHTML = `
      <span><strong>${candidate.symbol}</strong><em>${candidate.expiration_date} ${formatNumber(candidate.strike_price)} ${candidate.contract_type}</em></span>
      <span>${formatCurrency(candidate.close)}</span>
      <span>${formatPercent(candidate.day_change_pct)}</span>
      <span>${formatNumber(candidate.volume || 0)} vol</span>
      <span>${formatNumber(candidate.replay_score)}</span>
    `;
    row.addEventListener("click", () => {
      isInspectingContract = true;
      autoRefresh.checked = false;
      scheduleRefresh();
      paperOrderForm.elements.symbol.value = candidate.symbol;
      paperOrderForm.elements.side.value = "buy";
      paperOrderForm.elements.qty.value = "1";
      paperOrderForm.elements.type.value = "limit";
      paperOrderForm.elements.limit_price.value = candidate.close ? Number(candidate.close).toFixed(2) : "";
      setAlpacaStatus(`Staged ${candidate.symbol} from replay at ${payload.selected_time}.`, false);
    });
    fields.contractList.appendChild(row);
  }
}

function initializeReplayControls() {
  const today = new Date();
  const priorDay = new Date(today);
  priorDay.setDate(today.getDate() - 1);
  while (priorDay.getDay() === 0 || priorDay.getDay() === 6) {
    priorDay.setDate(priorDay.getDate() - 1);
  }
  replayDate.value = priorDay.toISOString().slice(0, 10);
  updateReplayClock();
  for (const button of speedButtons) {
    button.classList.toggle("active", Number(button.dataset.speed) === replaySpeed);
  }
}

function updateReplayClock() {
  const seconds = Number(replayTime.value || 57540);
  replayClock.textContent = formatClock(seconds);
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
      return;
    }
    const nextValue = Math.min(Number(replayTime.value) + replaySpeed, Number(replayTime.max));
    replayTime.value = String(nextValue);
    updateReplayClock();
    loadOptionReplay();
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

  if (!payload.candidates || payload.candidates.length === 0) {
    fields.contractList.textContent = "No contract candidates.";
    return;
  }

  fields.contractList.innerHTML = "";
  for (const candidate of payload.candidates) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "contract-row";
    row.innerHTML = `
      <span><strong>${candidate.symbol}</strong><em>${candidate.expiration_date} ${formatNumber(candidate.strike_price)} ${candidate.contract_type}</em></span>
      <span>${formatCurrency(candidate.mid)}</span>
      <span>${formatPercent(candidate.spread_pct)}</span>
      <span>${candidate.open_interest ?? "n/a"} OI</span>
      <span>${formatNumber(candidate.score)}</span>
    `;
    row.addEventListener("click", () => {
      isInspectingContract = true;
      autoRefresh.checked = false;
      scheduleRefresh();
      paperOrderForm.elements.symbol.value = candidate.symbol;
      paperOrderForm.elements.side.value = "buy";
      paperOrderForm.elements.qty.value = "1";
      paperOrderForm.elements.type.value = "limit";
      paperOrderForm.elements.limit_price.value = candidate.mid ? candidate.mid.toFixed(2) : "";
      setAlpacaStatus(`Staged ${candidate.symbol} as a paper limit order.`, false);
    });
    fields.contractList.appendChild(row);
  }
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

function setAlpacaStatus(message, isError) {
  alpacaStatus.textContent = message;
  alpacaStatus.classList.toggle("error", isError);
}


function setStatus(message, isError) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
