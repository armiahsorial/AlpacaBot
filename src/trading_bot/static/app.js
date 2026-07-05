const form = document.querySelector("#analysis-form");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const button = document.querySelector("#analyze-button");
const autoRefresh = document.querySelector("#auto-refresh");
const refreshSeconds = document.querySelector("#refresh-seconds");
let refreshTimer = null;
let lastAnalysis = null;
let isAnalysisRunning = false;

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
  scheduleRefresh();
});

refreshSeconds.addEventListener("change", () => {
  scheduleRefresh();
});

async function runAnalysis({ isRefresh = false } = {}) {
  if (isAnalysisRunning) {
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


function setStatus(message, isError) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
