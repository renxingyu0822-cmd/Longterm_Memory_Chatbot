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
  const filteredWatchlist = filterItems(state.dashboard.watchlist_only);
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
  const predictions = (item.predictions || []).map(value => `<span class="prediction-chip">${escapeHtml(predictionLabel(value))}</span>`).join("");
  const positionMeta = isPosition
    ? `<div class="profit ${directionClass(item.total_profit)}">总收益 ${formatNumber(item.total_profit)} ${escapeHtml(item.currency)} · ${formatPercent(item.return_percent)}</div>`
    : `<div class="asset-change ${directionClass(change)}">${formatPercent(change)}</div>`;
  const actions = isPosition
    ? `<button class="ghost-button small-button" data-action="trade" data-id="${item.id}">录入交易</button>`
    : `<button class="ghost-button small-button" data-action="trade" data-id="${item.id}">转为持仓</button><button class="danger-button small-button" data-action="remove-watch" data-id="${item.id}">移出自选</button>`;
  return `<article class="asset-row">
    <div><a class="asset-name" href="/market/asset/${item.id}">${escapeHtml(item.name)}</a><div class="asset-symbol">${escapeHtml(item.symbol)} · ${escapeHtml(subclassLabel(item.subclass))}${item.quote_source === "demo" || item.source === "demo" ? ' · <span class="source-demo">演示</span>' : ""}</div></div>
    <div><div class="asset-price">${formatNumber(price, price && price < 10 ? 4 : 2)} ${escapeHtml(item.currency)}</div>${positionMeta}</div>
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
  $("#list-copy").textContent = isPosition ? "成本、收益与实时预测" : "只观察，不计入持仓收益";
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

function localDateTimeValue() {
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  return now.toISOString().slice(0, 16);
}

function openTransaction(asset) {
  state.transactionAsset = asset;
  $("#transaction-asset-id").value = asset.id || "";
  $("#transaction-asset-name").value = `${asset.name} (${asset.symbol})`;
  $("#transaction-time").value = localDateTimeValue();
  $("#transaction-type").value = asset.subclass === "otc" ? "subscribe" : "buy";
  $("#transaction-quantity").value = "";
  $("#transaction-price").value = asset.current_price || asset.price || "";
  $("#transaction-cash").value = "";
  $("#transaction-fees").value = "0";
  $("#transaction-taxes").value = "0";
  $("#transaction-fx").value = "1";
  $("#transaction-note").value = "";
  $("#transaction-error").textContent = "";
  syncTransactionFields();
  $("#transaction-modal").classList.remove("hidden");
}

function closeTransaction() {
  $("#transaction-modal").classList.add("hidden");
  state.transactionAsset = null;
}

function syncTransactionFields() {
  const cashOnly = ["dividend", "fee"].includes($("#transaction-type").value);
  $$('[data-trade-field]').forEach(element => element.hidden = cashOnly);
  $$('[data-cash-field]').forEach(element => element.hidden = !cashOnly);
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
  $$("[data-asset-class]").forEach(button => button.classList.toggle("active", button.dataset.assetClass === assetClass));
  $("#stock-subtabs").hidden = assetClass !== "stock";
  $("#fund-subtabs").hidden = assetClass !== "fund";
  $$(".subtab").forEach(button => button.classList.toggle("active", button.dataset.subclass === "all"));
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
  $("#search-results").innerHTML = "";
  renderDashboard();
}));
$$("[data-view]").forEach(button => button.addEventListener("click", () => {
  state.view = button.dataset.view;
  $$("[data-view]").forEach(item => item.classList.toggle("active", item === button));
  renderList();
}));
$("#search-button").addEventListener("click", searchAssets);
$("#asset-search").addEventListener("keydown", event => { if (event.key === "Enter") searchAssets(); });
$("#transaction-close").addEventListener("click", closeTransaction);
$("#transaction-cancel").addEventListener("click", closeTransaction);
$("#transaction-type").addEventListener("change", syncTransactionFields);
$("#transaction-form").addEventListener("submit", submitTransaction);
$("#transaction-modal").addEventListener("click", event => { if (event.target === $("#transaction-modal")) closeTransaction(); });

loadDashboard().catch(error => {
  $("#asset-list").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
});
connectStream();

