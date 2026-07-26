const WORKSPACE_STATE_KEY = "thumper-market-workspace-v1";
const TRANSACTION_DRAFT_KEY = "thumper-market-transaction-draft-v1";
const TRANSACTION_FIELD_IDS = [
  "transaction-type",
  "transaction-time",
  "transaction-quantity",
  "transaction-price",
  "transaction-cash",
  "transaction-fees",
  "transaction-taxes",
  "transaction-fx",
  "transaction-note",
];

const state = {
  assetClass: "stock",
  subclass: "all",
  view: "positions",
  dashboard: { positions: [], watchlist: [], watchlist_only: [], summary: {}, tracked_count: 0 },
  transactionAsset: null,
};

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${formatNumber(number)}%`;
}

function directionClass(value) {
  const number = Number(value || 0);
  return number > 0 ? "positive" : number < 0 ? "negative" : "neutral";
}

function subclassLabel(value) {
  return { cn: "A股", hk: "港股", us: "美股", exchange_traded: "场内基金", otc: "场外基金" }[value] || value;
}

function readSession(key) {
  try {
    const value = sessionStorage.getItem(key);
    return value ? JSON.parse(value) : null;
  } catch (error) {
    return null;
  }
}

function writeSession(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    // The workspace remains usable when storage is unavailable.
  }
}

function removeSession(key) {
  try {
    sessionStorage.removeItem(key);
  } catch (error) {
    // The workspace remains usable when storage is unavailable.
  }
}

function saveWorkspaceState() {
  writeSession(WORKSPACE_STATE_KEY, {
    assetClass: state.assetClass,
    subclass: state.subclass,
    view: state.view,
  });
}

function restoreWorkspaceState() {
  const saved = readSession(WORKSPACE_STATE_KEY);
  if (!saved) return;
  if (["stock", "fund"].includes(saved.assetClass)) state.assetClass = saved.assetClass;
  const allowedSubclasses = state.assetClass === "fund"
    ? ["all", "exchange_traded", "otc"]
    : ["all", "cn", "hk", "us"];
  if (allowedSubclasses.includes(saved.subclass)) state.subclass = saved.subclass;
  if (["positions", "watchlist_only"].includes(saved.view)) state.view = saved.view;
}

function applyWorkspaceState() {
  $$('[data-asset-class]').forEach(button => {
    button.classList.toggle("active", button.dataset.assetClass === state.assetClass);
  });
  $("#stock-subtabs").hidden = state.assetClass !== "stock";
  $("#fund-subtabs").hidden = state.assetClass !== "fund";
  const activeSubtabs = state.assetClass === "fund" ? $("#fund-subtabs") : $("#stock-subtabs");
  $$(".subtab").forEach(button => button.classList.remove("active"));
  activeSubtabs.querySelector(`[data-subclass="${state.subclass}"]`)?.classList.add("active");
  $$('[data-view]').forEach(button => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });
}

function predictionLabel(item) {
  if (!item) return "暂无预测";
  const probabilities = [
    ["上涨", Number(item.probability_up)],
    ["震荡", Number(item.probability_flat)],
    ["下跌", Number(item.probability_down)],
  ];
  const winner = probabilities.sort((a, b) => b[1] - a[1])[0];
  return `${item.horizon_days}日 ${winner[0]} ${Math.round(winner[1] * 100)}%`;
}

function filterItems(items) {
  return (items || []).filter(item => {
    if (item.asset_class !== state.assetClass) return false;
    return state.subclass === "all" || item.subclass === state.subclass;
  });
}

function renderSummary() {
  const filteredPositions = filterItems(state.dashboard.positions);
  const filteredWatchlist = filterItems(state.dashboard.watchlist);
  $("#position-count").textContent = filteredPositions.length;
  $("#watchlist-count").textContent = filteredWatchlist.length;
  $("#tracked-count").textContent = state.dashboard.tracked_count || 0;
  const totals = {};
  filteredPositions.forEach(item => {
    totals[item.currency] = (totals[item.currency] || 0) + Number(item.total_profit || 0);
  });
  const entries = Object.entries(totals);
  $("#profit-total").textContent = entries.length === 1 ? `${formatNumber(entries[0][1])} ${entries[0][0]}` : entries.length ? "多币种" : "—";
  $("#profit-total").className = `summary-value ${entries.length === 1 ? directionClass(entries[0][1]) : ""}`;
  $("#profit-currency").textContent = entries.length > 1 ? entries.map(([currency, value]) => `${currency} ${formatNumber(value)}`).join(" · ") : "按当前分类统计";
}

function rowHtml(item, isPosition) {
  const price = isPosition ? item.current_price : item.price;
  const change = item.change_percent;
  const priceLabel = item.asset_class === "fund"
    ? (item.subclass === "otc" ? "最新单位净值" : "基金最新价")
    : "最新价";
  const predictions = (item.predictions || []).map(value => `<span class="prediction-chip">${escapeHtml(predictionLabel(value))}</span>`).join("");
  const positionMeta = isPosition
    ? `<div class="profit ${directionClass(item.total_profit)}">总收益 ${formatNumber(item.total_profit)} ${escapeHtml(item.currency)} · ${formatPercent(item.return_percent)}</div>`
    : `<div class="asset-change ${directionClass(change)}">${formatPercent(change)}</div>`;
  const actions = isPosition
    ? `<button class="ghost-button small-button" data-action="trade" data-id="${item.id}">录入交易</button>`
    : `<button class="ghost-button small-button" data-action="trade" data-id="${item.id}">转为持仓</button><button class="danger-button small-button" data-action="remove-watch" data-id="${item.id}">移出自选</button>`;
  return `<article class="asset-row">
    <div><a class="asset-name" href="/market/asset/${item.id}">${escapeHtml(item.name)}</a><div class="asset-symbol">${escapeHtml(item.symbol)} · ${escapeHtml(subclassLabel(item.subclass))}${item.quote_source === "demo" || item.source === "demo" ? ' · <span class="source-demo">演示</span>' : ""}</div></div>
    <div><div class="asset-price-label">${priceLabel}</div><div class="asset-price">${formatNumber(price, price && price < 10 ? 4 : 2)} ${escapeHtml(item.currency)}</div>${positionMeta}</div>
    <div class="prediction-mini">${predictions || '<span class="prediction-chip">等待足够历史数据</span>'}</div>
    <div class="row-actions">${actions}</div>
  </article>`;
}

function bindRowActions() {
  $$('[data-action="trade"]').forEach(button => button.addEventListener("click", () => {
    const id = Number(button.dataset.id);
    const asset = [...state.dashboard.positions, ...state.dashboard.watchlist].find(item => Number(item.id) === id);
    if (asset) openTransaction(asset);
  }));
  $$('[data-action="remove-watch"]').forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    await fetch(`/api/market/watchlist/${button.dataset.id}`, { method: "DELETE" });
    await loadDashboard();
  }));
}

function renderList() {
  const items = filterItems(state.dashboard[state.view]);
  const isPosition = state.view === "positions";
  $("#list-title").textContent = isPosition ? "持有中" : "仅自选";
  if (state.assetClass === "fund") {
    $("#list-copy").textContent = isPosition ? "份额、净值、收益与趋势观察" : "只观察基金净值，不计入持仓收益";
  } else {
    $("#list-copy").textContent = isPosition ? "成本、收益与实时预测" : "只观察，不计入持仓收益";
  }
  $("#asset-list").innerHTML = items.length
    ? items.map(item => rowHtml(item, isPosition)).join("")
    : `<div class="empty-state"><span class="empty-icon">${isPosition ? "◎" : "⌁"}</span>${isPosition ? "当前分类还没有持仓，可从右侧搜索并录入第一笔交易。" : "当前分类还没有纯自选资产。"}</div>`;
  bindRowActions();
}

function renderDashboard() {
  renderSummary();
  renderList();
}

async function loadDashboard() {
  const response = await fetch("/api/market/dashboard");
  if (!response.ok) throw new Error("无法读取投资数据");
  state.dashboard = await response.json();
  renderDashboard();
}

function renderSearch(results) {
  $("#search-results").innerHTML = results.length ? results.map((item, index) => `<article class="search-item">
    <div><div class="search-name">${escapeHtml(item.name)}</div><div class="search-meta">${escapeHtml(item.symbol)} · ${escapeHtml(subclassLabel(item.subclass))} · ${escapeHtml(item.currency)}${item.source === "demo" ? ' · <span class="source-demo">演示数据</span>' : ""}</div></div>
    <div class="row-actions"><button class="ghost-button small-button" data-search-action="watch" data-index="${index}">加自选</button><button class="primary-button small-button" data-search-action="hold" data-index="${index}">录持仓</button></div>
  </article>`).join("") : '<div class="empty-state">没有找到符合当前分类的资产。</div>';
  $$('[data-search-action="watch"]').forEach(button => button.addEventListener("click", () => addWatchlist(results[Number(button.dataset.index)], button)));
  $$('[data-search-action="hold"]').forEach(button => button.addEventListener("click", () => openTransaction(results[Number(button.dataset.index)])));
}

async function searchAssets() {
  const button = $("#search-button");
  button.disabled = true;
  $("#search-results").innerHTML = '<div class="empty-state">正在搜索…</div>';
  const params = new URLSearchParams({ q: $("#asset-search").value.trim(), asset_class: state.assetClass });
  if (state.subclass !== "all") params.set("subclass", state.subclass);
  try {
    const response = await fetch(`/api/market/search?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "搜索失败");
    renderSearch(data.results || []);
  } catch (error) {
    $("#search-results").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  } finally {
    button.disabled = false;
  }
}

async function addWatchlist(asset, button) {
  button.disabled = true;
  try {
    const response = await fetch("/api/market/watchlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ asset }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "添加失败");
    await loadDashboard();
    button.textContent = "已添加";
  } catch (error) {
    button.disabled = false;
    button.textContent = "重试";
  }
}

function setImportBusy(busy) {
  $$('[data-import-target]').forEach(button => { button.disabled = busy; });
}

function renderImportResult(data) {
  const status = $("#portfolio-import-status");
  const imported = Number(data.imported_count || 0);
  const failed = Number(data.failed_count || 0);
  const holdingNote = data.target === "holdings" && imported ? "，并已同步加入自选" : "";
  const errors = (data.errors || []).slice(0, 4).map(item =>
    `<li>${escapeHtml(item.label)}：${escapeHtml(item.error)}</li>`
  ).join("");
  status.className = `import-status ${imported ? "success" : "error"}`;
  status.innerHTML = `已导入 ${imported} 项${holdingNote}${failed ? `，${failed} 项未导入` : ""}${errors ? `<ul class="import-error-list">${errors}</ul>` : ""}`;
}

async function importPortfolioFile(file, target) {
  const status = $("#portfolio-import-status");
  setImportBusy(true);
  status.className = "import-status";
  status.textContent = file.type.startsWith("image/") || file.name.toLowerCase().endsWith(".pdf")
    ? "正在识别并匹配资产…"
    : "正在读取并匹配资产…";
  const form = new FormData();
  form.append("target", target);
  form.append("file", file);
  try {
    const response = await fetch("/api/portfolio/import", { method: "POST", body: form });
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      // Flask's default 404/500 pages are HTML. Parsing them as JSON hides the
      // useful HTTP status behind an "Unexpected token '<'" browser error.
      await response.text();
      if (response.status === 404) {
        throw new Error("导入接口尚未加载，请重启本地服务后重试");
      }
      throw new Error(`导入服务返回异常响应（HTTP ${response.status}）`);
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "导入失败");
    state.dashboard = data.dashboard;
    state.view = target === "holdings" ? "positions" : "watchlist_only";
    saveWorkspaceState();
    applyWorkspaceState();
    renderDashboard();
    renderImportResult(data);
  } catch (error) {
    status.className = "import-status error";
    status.textContent = error.message;
  } finally {
    setImportBusy(false);
  }
}

function localDateTimeValue() {
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  return now.toISOString().slice(0, 16);
}

function transactionValues() {
  return Object.fromEntries(TRANSACTION_FIELD_IDS.map(id => [id, $(`#${id}`).value]));
}

function saveTransactionDraft() {
  if (!state.transactionAsset || $("#transaction-modal").classList.contains("hidden")) return;
  const assetKeys = [
    "id", "symbol", "provider_symbol", "name", "asset_class", "subclass",
    "market", "exchange", "currency", "timezone", "source", "price", "current_price",
  ];
  const asset = Object.fromEntries(assetKeys
    .filter(key => state.transactionAsset[key] !== undefined)
    .map(key => [key, state.transactionAsset[key]]));
  writeSession(TRANSACTION_DRAFT_KEY, { asset, values: transactionValues() });
}

function applyTransactionPresentation(asset) {
  const isFund = asset.asset_class === "fund";
  const isOtcFund = isFund && asset.subclass === "otc";
  $("#transaction-title").textContent = isFund ? "录入基金交易" : "录入股票交易";
  $("#transaction-quantity-label").textContent = isFund ? "基金份额" : "股票数量";
  $("#transaction-price-label").textContent = isOtcFund ? "单位净值" : "成交单价";

  const allowedTypes = isOtcFund
    ? new Set(["subscribe", "redeem", "dividend", "fee"])
    : new Set(["buy", "sell", "dividend", "fee"]);
  [...$("#transaction-type").options].forEach(option => {
    option.hidden = !allowedTypes.has(option.value);
    option.disabled = !allowedTypes.has(option.value);
  });
}

function openTransaction(asset, savedValues = null) {
  state.transactionAsset = asset;
  applyTransactionPresentation(asset);
  $("#transaction-asset-id").value = asset.id || "";
  $("#transaction-asset-name").value = `${asset.name} (${asset.symbol}) · ${subclassLabel(asset.subclass)}`;
  const defaults = {
    "transaction-time": localDateTimeValue(),
    "transaction-type": asset.subclass === "otc" ? "subscribe" : "buy",
    "transaction-quantity": "",
    "transaction-price": asset.current_price || asset.price || "",
    "transaction-cash": "",
    "transaction-fees": "0",
    "transaction-taxes": "0",
    "transaction-fx": "1",
    "transaction-note": "",
  };
  TRANSACTION_FIELD_IDS.forEach(id => {
    $(`#${id}`).value = savedValues?.[id] ?? defaults[id] ?? "";
  });
  $("#transaction-error").textContent = "";
  syncTransactionFields();
  $("#transaction-modal").classList.remove("hidden");
  saveTransactionDraft();
}

function closeTransaction() {
  $("#transaction-modal").classList.add("hidden");
  state.transactionAsset = null;
  removeSession(TRANSACTION_DRAFT_KEY);
}

function syncTransactionFields() {
  const cashOnly = ["dividend", "fee"].includes($("#transaction-type").value);
  $$('[data-trade-field]').forEach(element => element.hidden = cashOnly);
  $$('[data-cash-field]').forEach(element => element.hidden = !cashOnly);
  saveTransactionDraft();
}

function restoreTransactionDraft() {
  const draft = readSession(TRANSACTION_DRAFT_KEY);
  if (!draft?.asset || !draft?.values) return;
  if (!["stock", "fund"].includes(draft.asset.asset_class)) {
    removeSession(TRANSACTION_DRAFT_KEY);
    return;
  }
  openTransaction(draft.asset, draft.values);
}

async function submitTransaction(event) {
  event.preventDefault();
  const asset = state.transactionAsset;
  if (!asset) return;
  const button = $("#transaction-submit");
  button.disabled = true;
  $("#transaction-error").textContent = "";
  const payload = {
    transaction_type: $("#transaction-type").value,
    occurred_at: new Date($("#transaction-time").value).toISOString(),
    quantity: Number($("#transaction-quantity").value || 0),
    price: Number($("#transaction-price").value || 0),
    cash_amount: Number($("#transaction-cash").value || 0),
    fees: Number($("#transaction-fees").value || 0),
    taxes: Number($("#transaction-taxes").value || 0),
    fx_rate: Number($("#transaction-fx").value || 1),
    currency: asset.currency,
    note: $("#transaction-note").value.trim(),
  };
  if (asset.id) payload.asset_id = Number(asset.id); else payload.asset = asset;
  try {
    const response = await fetch("/api/portfolio/transactions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "保存失败");
    state.dashboard = data.dashboard;
    closeTransaction();
    renderDashboard();
  } catch (error) {
    $("#transaction-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function setAssetClass(assetClass) {
  state.assetClass = assetClass;
  state.subclass = "all";
  saveWorkspaceState();
  applyWorkspaceState();
  $("#search-results").innerHTML = "";
  renderDashboard();
}

function connectStream() {
  const source = new EventSource("/api/market/stream");
  source.addEventListener("open", () => {
    $("#live-dot").classList.add("connected");
    $("#live-label").textContent = "行情追踪已连接";
  });
  source.addEventListener("market_update", event => {
    const payload = JSON.parse(event.data);
    if (payload.dashboard) {
      state.dashboard = payload.dashboard;
      renderDashboard();
    }
    $("#live-meta").textContent = `最近刷新 ${new Date().toLocaleTimeString("zh-CN")} · 最长约 60 秒`;
  });
  source.onerror = () => {
    $("#live-dot").classList.remove("connected");
    $("#live-label").textContent = "行情正在重连";
  };
}

$$("[data-asset-class]").forEach(button => button.addEventListener("click", () => setAssetClass(button.dataset.assetClass)));
$$(".subtab").forEach(button => button.addEventListener("click", () => {
  const parent = button.parentElement;
  [...parent.querySelectorAll(".subtab")].forEach(item => item.classList.toggle("active", item === button));
  state.subclass = button.dataset.subclass;
  saveWorkspaceState();
  $("#search-results").innerHTML = "";
  renderDashboard();
}));
$$("[data-view]").forEach(button => button.addEventListener("click", () => {
  state.view = button.dataset.view;
  saveWorkspaceState();
  $$("[data-view]").forEach(item => item.classList.toggle("active", item === button));
  renderList();
}));
$("#search-button").addEventListener("click", searchAssets);
$("#asset-search").addEventListener("keydown", event => { if (event.key === "Enter") searchAssets(); });
$$('[data-import-target]').forEach(button => button.addEventListener("click", () => {
  const input = $("#portfolio-import-file");
  input.dataset.target = button.dataset.importTarget;
  input.value = "";
  input.click();
}));
$("#portfolio-import-file").addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) importPortfolioFile(file, event.target.dataset.target || "holdings");
});
$("#transaction-close").addEventListener("click", closeTransaction);
$("#transaction-cancel").addEventListener("click", closeTransaction);
$("#transaction-type").addEventListener("change", syncTransactionFields);
TRANSACTION_FIELD_IDS.forEach(id => {
  $(`#${id}`).addEventListener("input", saveTransactionDraft);
  $(`#${id}`).addEventListener("change", saveTransactionDraft);
});
$("#transaction-form").addEventListener("submit", submitTransaction);
$("#transaction-modal").addEventListener("click", event => { if (event.target === $("#transaction-modal")) closeTransaction(); });
window.addEventListener("beforeunload", () => {
  saveWorkspaceState();
  saveTransactionDraft();
});

restoreWorkspaceState();
applyWorkspaceState();
restoreTransactionDraft();
loadDashboard().catch(error => {
  $("#asset-list").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
});
connectStream();
