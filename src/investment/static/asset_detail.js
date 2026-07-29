const assetId = Number(document.body.dataset.assetId);
const $ = selector => document.querySelector(selector);

function number(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function percent(value, signed = true) {
  if (value === null || value === undefined) return "—";
  const numeric = Number(value);
  return `${signed && numeric > 0 ? "+" : ""}${number(numeric)}%`;
}

function subclassLabel(value) {
  return { cn: "A股", hk: "港股", us: "美股", exchange_traded: "场内基金", otc: "场外基金" }[value] || value;
}

function metric(label, value) {
  return `<div class="metric-row"><span>${label}</span><strong>${value}</strong></div>`;
}

function renderChart(history) {
  if (!history || history.length < 2) return;
  const values = history.map(item => Number(item.close));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const points = values.map((value, index) => {
    const x = index / (values.length - 1) * 800;
    const y = 235 - (value - minimum) / range * 215;
    return [x, y];
  });
  $("#chart-line").setAttribute("points", points.map(point => point.join(",")).join(" "));
  $("#chart-area").setAttribute("d", `M ${points[0][0]} 250 L ${points.map(point => point.join(" ")).join(" L ")} L ${points.at(-1)[0]} 250 Z`);
}

function renderPredictions(predictions, isOtcFund) {
  $("#detail-predictions").innerHTML = predictions.length ? predictions.map(item => {
    const up = Number(item.probability_up);
    const down = Number(item.probability_down);
    const directionalTotal = up + down;
    const probabilityUp = isOtcFund ? (directionalTotal > 0 ? up / directionalTotal : 0.5) : up;
    const probabilityDown = isOtcFund ? (directionalTotal > 0 ? down / directionalTotal : 0.5) : down;
    const choices = isOtcFund
      ? [["上涨", probabilityUp], ["下跌", probabilityDown]].sort((a,b) => b[1] - a[1])
      : [["上涨", probabilityUp], ["震荡", Number(item.probability_flat)], ["下跌", probabilityDown]].sort((a,b) => b[1] - a[1]);
    const probabilityRows = isOtcFund
      ? `<span>涨 ${Math.round(probabilityUp*100)}%</span><span>跌 ${Math.round(probabilityDown*100)}%</span>`
      : `<span>涨 ${Math.round(probabilityUp*100)}%</span><span>震荡 ${Math.round(item.probability_flat*100)}%</span><span>跌 ${Math.round(probabilityDown*100)}%</span>`;
    const horizonLabel = isOtcFund
      ? `${item.horizon_days} 个交易日 · 期末净值相对期初`
      : `未来 ${item.horizon_days} 个交易日`;
    return `<article class="prediction-card"><div class="prediction-horizon">${horizonLabel} · ${item.confidence || "low"}</div><div class="probability-main">${choices[0][0]} ${Math.round(choices[0][1] * 100)}%</div><div class="probability-row">${probabilityRows}</div><div class="quote-meta">预计区间 ${percent(item.expected_low)} ～ ${percent(item.expected_high)}</div></article>`;
  }).join("") : '<div class="empty-state">历史数据不足，暂不生成预测。</div>';
}

function renderBacktest(performance) {
  const rows = Object.entries(performance || {});
  $("#detail-backtest").innerHTML = rows.length ? `<table class="backtest-table"><thead><tr><th>周期</th><th>样本</th><th>命中率</th><th>平衡准确率</th><th>高信心覆盖</th></tr></thead><tbody>${rows.map(([horizon,item]) => `<tr><td>${horizon}日</td><td>${item.sample_count}</td><td>${percent(item.accuracy, false)}</td><td>${percent(item.balanced_accuracy, false)}</td><td>${percent(item.high_confidence_coverage, false)}</td></tr>`).join("")}</tbody></table>` : '<div class="empty-state">回测样本不足。</div>';
}

function render(data) {
  const quote = data.quote || {};
  const isFund = data.asset_class === "fund";
  const isOtcFund = isFund && data.subclass === "otc";
  $("#asset-title").textContent = data.name;
  document.title = `Thumper · ${data.name}`;
  $("#asset-meta").textContent = `${data.symbol} · ${subclassLabel(data.subclass)} · ${data.exchange || data.market} · ${data.currency}`;
  $("#asset-source").textContent = quote.source === "demo" ? "当前为演示数据，仅用于验证功能，不可用于投资判断。" : "概率、回测和模拟均为研究工具，不构成投资建议。";
  $("#detail-price").textContent = `${number(quote.price, quote.price < 10 ? 4 : 2)} ${quote.currency || data.currency}`;
  if (isOtcFund) {
    $("#detail-quote-meta").textContent = `净值日期 ${quote.quote_time || "—"} · 场外基金正式单位净值 · 延迟公布`;
  } else if (isFund) {
    $("#detail-quote-meta").textContent = `行情时间 ${quote.quote_time || "—"} · 涨跌 ${percent(quote.change_percent)} · 场内基金行情`;
  } else {
    $("#detail-quote-meta").textContent = `行情时间 ${quote.quote_time || "—"} · 涨跌 ${percent(quote.change_percent)} · ${quote.is_delayed ? "延迟行情" : "实时行情"}`;
  }
  renderChart(data.history || []);
  renderPredictions(data.predictions || [], isOtcFund);
  renderBacktest(data.performance || {});
  $("#prediction-disclaimer").textContent = isOtcFund
    ? "场外基金保留 1、3、5、20 个交易日预测，且每个周期只分上涨或下跌；方向表示周期结束时的正式单位净值相对周期开始时的正式单位净值。"
    : "预测周期为未来 1、3、5、20 个交易日。实时推断只更新特征，不在页面请求中重新训练模型。";
  $("#backtest-disclaimer").textContent = isOtcFund
    ? "场外基金回测使用相同的期末净值相对期初净值口径；净值不变的样本不计入二分类命中率。"
    : "回测与上线后的真实预测记录应分开理解；命中率不等于收益率。";

  const risk = data.risk || {};
  const riskLabel = { low: "较低", medium: "中等", high: "较高", insufficient_data: "数据不足" }[risk.risk_level] || "—";
  $("#detail-risk").innerHTML = metric("风险等级", riskLabel) + metric("年化波动率", percent(risk.annualized_volatility, false)) + metric("最大回撤", percent(risk.max_drawdown)) + metric("下跌日占比", percent(risk.downside_frequency, false));
  const simulation = data.simulation || {};
  $("#simulation-card").hidden = isOtcFund;
  $("#detail-simulation").innerHTML = Object.keys(simulation).length ? metric("策略收益", percent(simulation.strategy_return)) + metric("买入持有", percent(simulation.buy_hold_return)) + metric("超额收益", percent(simulation.excess_return)) + metric("最大回撤", percent(simulation.max_drawdown)) + metric("交易成本", percent((simulation.transaction_cost || 0) * 100, false)) : metric("状态", "样本不足");
  $("#detail-data").innerHTML = metric("资产类型", subclassLabel(data.subclass)) + metric(isOtcFund ? "净值来源" : "行情来源", quote.source || data.source || "—") + metric(isOtcFund ? "净值日期" : "行情时间", quote.quote_time || "—") + metric("接收时间", quote.received_at || "—") + (isOtcFund ? metric("预测口径", "周期末正式净值 vs 周期初正式净值") : "") + metric("模型版本", (data.predictions || [])[0]?.model_version || (isOtcFund ? "otc-nav-direction-v1" : "transparent-momentum-v1")) + metric("历史样本", String((data.history || []).length));
}

async function load(refresh = false) {
  const button = $("#refresh-asset");
  button.disabled = true;
  try {
    const response = await fetch(`/api/market/assets/${assetId}${refresh ? "?refresh=1" : ""}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "加载失败");
    render(data);
  } catch (error) {
    $("#asset-source").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

$("#refresh-asset").addEventListener("click", () => load(true));
load();
