/**
 * #publisher/<id> — a publisher's class, read from its article predictions.
 *
 * Nothing here is stored: the user picks how the article verdicts are counted and
 * which articles take part, and the backend recomputes everything on each change. The
 * charts are redrawn from the same payload that produced the numbers, so a figure can
 * never drift away from the table beside it.
 */

import {api} from "../api.js";
import {CHART_TYPES} from "../charts.js";
import {errorCard, pager, probabilityCells, table} from "../components.js";
import {escapeHtml, modelLabel, provenanceLabel, shortId} from "../format.js";
import {content, mount} from "../view.js";

const RUNS_PAGE_SIZE = 100;

/** Percentage with no false precision; an absent value stays absent. */
const percent = (value) =>
  value === null || value === undefined ? "—" : `${(Number(value) * 100).toFixed(0)}%`;

const decimal = (value, places = 3) =>
  value === null || value === undefined ? "—" : Number(value).toFixed(places);

function storedPredictionRow(run) {
  return `<tr><td><a class="url detail-link" href="#article/${encodeURIComponent(run.article_id)}" title="${escapeHtml(run.canonical_url)}">${escapeHtml(run.canonical_url)}</a></td>
        <td><b>${escapeHtml(modelLabel(run))}</b><br><span class="muted">${escapeHtml(provenanceLabel(run.model_provenance))}</span></td>
        <td><span class="class-chip">${run.predicted_class}</span></td>${probabilityCells(run)}
        <td>${shortId(run.prediction_run_id)}</td></tr>`;
}

/**
 * The dispersion warning that sits beside a verdict.
 *
 * A class on its own reads as a fact. The band is what stops it from doing so, which
 * is why it is rendered next to the class rather than in a footnote.
 */
function dispersionPill(group) {
  if (!group.dispersion_band) return "";
  return `<span class="dispersion-pill ${escapeHtml(group.dispersion_band)}" title="${escapeHtml(group.dispersion_note || "")}">
    ${escapeHtml(group.dispersion_band)} · variance ${decimal(group.variance)}</span>`;
}

/** One card per measurement: the verdict, how much the articles agreed, and why. */
function verdictCard(group) {
  if (group.result_class === null) {
    return `<article class="verdict-card unavailable">
      <header><b>${escapeHtml(group.display_name)}</b>
        <span class="muted">${escapeHtml(provenanceLabel(group.provenance))}</span></header>
      <p class="muted">${escapeHtml(group.unavailable_reason || "No class available.")}</p>
      <p class="muted">${group.used_count} of ${group.available_count} articles counted.</p>
    </article>`;
  }
  const excluded = group.excluded_count
    ? ` · ${group.excluded_count} left out`
    : "";
  return `<article class="verdict-card">
    <header><b>${escapeHtml(group.display_name)}</b>
      <span class="muted">${escapeHtml(provenanceLabel(group.provenance))}</span></header>
    <div class="verdict-class"><span class="class-chip large">Class ${group.result_class}</span>${dispersionPill(group)}</div>
    <dl class="verdict-stats">
      <div><dt>Articles counted</dt><dd>${group.used_count} of ${group.available_count}${escapeHtml(excluded)}</dd></div>
      <div><dt>Articles in this class</dt><dd>${percent(group.agreement)}</dd></div>
      <div><dt>Within one class</dt><dd>${percent(group.tolerant_agreement)}</dd></div>
      <div><dt>Mean class</dt><dd class="mono">${decimal(group.mean_class, 2)}</dd></div>
      <div><dt>Variance</dt><dd class="mono">${decimal(group.variance)}</dd></div>
      <div><dt>Variance allowing adjacent</dt><dd class="mono">${decimal(group.tolerant_variance)}</dd></div>
    </dl>
    <p class="verdict-note muted">${escapeHtml(group.dispersion_note || "")}</p>
  </article>`;
}

function aggregationResults(payload) {
  if (!payload.models.length) {
    return `<div class="empty notice">No leakage-safe prediction is stored for this publisher, so no class can be read for it.</div>`;
  }
  return `<div class="verdict-grid">${payload.models.map(verdictCard).join("")}</div>`;
}

export async function publisherDetailPage(id, params) {
  const offset = Number(params.get("offset") || 0);
  const [publisher, runs, methods] = await Promise.all([
    api(`/api/v1/publishers/${encodeURIComponent(id)}`),
    api(`/api/v1/prediction-runs?publisher_id=${encodeURIComponent(id)}&limit=${RUNS_PAGE_SIZE}&offset=${offset}`),
    api(`/api/v1/aggregation-methods`),
  ]);

  mount("publisher", {
    hostname: escapeHtml(publisher.normalized_hostname),
    articleCount: publisher.article_count,
    runCount: publisher.run_count,
    modelCount: publisher.model_count,
    storedPredictions: table(
      ["Article", "Model / fold", "Class", "P(0)", "P(1)", "P(2)", "P(3)", "P(4)", "Run"],
      runs.items.map(storedPredictionRow),
    ) + pager(`publisher/${encodeURIComponent(id)}`, runs.page, runs.items.length),
  });

  const methodField = content.querySelector("#aggregation-method");
  const formula = content.querySelector("#method-formula");
  const output = content.querySelector("#aggregation-results");
  const chartControls = content.querySelector("#chart-controls");
  const chartArea = content.querySelector("#chart-area");
  const exclusionList = content.querySelector("#exclusion-list");
  const excludedIds = new Set();
  let selectedChart = CHART_TYPES[0].id;
  let lastPayload = null;
  // Toggling several articles quickly, or changing the rule mid-request, leaves
  // more than one aggregation in flight. Responses can come back out of order, so
  // each request takes a ticket and only the newest one is allowed to draw:
  // otherwise the verdicts and charts could settle on a selection the checkboxes
  // no longer show.
  let latestRequest = 0;

  // The method list comes from the backend so the formulas shown here can never
  // disagree with the ones actually applied.
  methodField.innerHTML = methods.items
    .map(entry => `<option value="${escapeHtml(entry.method)}">${escapeHtml(entry.label || entry.method)}</option>`)
    .join("");

  /** Explain the chosen rule, so the number above it is never a mystery. */
  function describeMethod() {
    const entry = methods.items.find(item => item.method === methodField.value);
    if (!entry) return;
    formula.textContent = `${entry.description} ${entry.formula} ${entry.tie_rule}`;
  }

  chartControls.innerHTML = CHART_TYPES
    .map(chart => `<button type="button" class="segment" data-chart="${escapeHtml(chart.id)}" aria-pressed="${chart.id === selectedChart}">${escapeHtml(chart.label)}</button>`)
    .join("");

  /** Redraw the selected chart, once per measurement or once for the whole payload. */
  function drawCharts() {
    if (!lastPayload) return;
    const chart = CHART_TYPES.find(item => item.id === selectedChart);
    chartControls.querySelectorAll(".segment").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.chart === selectedChart));
    });
    chartArea.className = "chart-area";
    if (!lastPayload.models.length) {
      chartArea.innerHTML = `<p class="chart-empty muted">Nothing to plot without a counted prediction.</p>`;
      return;
    }
    const context = {bands: methods.dispersion_bands || []};
    chartArea.innerHTML = chart.scope === "payload"
      ? chart.draw(lastPayload, context)
      : lastPayload.models
          .map(group => `<div class="chart-slot"><h3>${escapeHtml(group.display_name)}</h3>${chart.draw(group, context)}</div>`)
          .join("");
  }

  /** One checkbox per article; unchecking it recounts every model without it. */
  function renderExclusionList(articles) {
    exclusionList.className = "exclusion-list";
    exclusionList.innerHTML = articles.map(item => `
      <label class="exclusion-item">
        <input type="checkbox" class="article-toggle" value="${escapeHtml(item.article_id)}"${item.excluded ? "" : " checked"}>
        <a class="url detail-link" href="#article/${encodeURIComponent(item.article_id)}" title="${escapeHtml(item.canonical_url)}">${escapeHtml(item.canonical_url)}</a>
      </label>`).join("");
    exclusionList.querySelectorAll(".article-toggle").forEach(box => {
      box.addEventListener("change", () => {
        if (box.checked) excludedIds.delete(box.value); else excludedIds.add(box.value);
        refresh();
      });
    });
  }

  /** Recompute the class. The article list is only rebuilt on the first call. */
  async function refresh(withArticles = false) {
    const ticket = ++latestRequest;
    const excluded = [...excludedIds]
      .map(value => `&exclude=${encodeURIComponent(value)}`).join("");
    output.className = "loading";
    output.textContent = "Reading the article predictions…";
    chartArea.className = "chart-area loading";
    chartArea.textContent = "Drawing…";
    try {
      const payload = await api(
        `/api/v1/publishers/${encodeURIComponent(id)}/aggregation`
        + `?method=${encodeURIComponent(methodField.value)}${excluded}`
      );
      if (ticket !== latestRequest) return;
      lastPayload = payload;
      output.className = "";
      output.innerHTML = aggregationResults(payload);
      drawCharts();
      if (withArticles) renderExclusionList(payload.articles);
    } catch (error) {
      if (ticket !== latestRequest) return;
      lastPayload = null;
      output.className = "";
      output.innerHTML = errorCard(error.message);
      chartArea.className = "chart-area";
      chartArea.innerHTML = "";
    }
  }

  chartControls.addEventListener("click", (event) => {
    const button = event.target.closest(".segment");
    if (!button) return;
    selectedChart = button.dataset.chart;
    drawCharts();
  });

  methodField.addEventListener("change", () => {
    describeMethod();
    refresh();
  });

  describeMethod();
  await refresh(true);
}
