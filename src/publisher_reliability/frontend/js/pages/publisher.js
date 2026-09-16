/**
 * #publisher/<id> — a publisher's class, read from its article predictions.
 *
 * Nothing here is stored: the user picks how the article verdicts are counted and
 * which articles take part, and the backend recomputes the class on every change.
 */

import {api} from "../api.js";
import {errorCard, pager, probabilityCells, table} from "../components.js";
import {escapeHtml, modelLabel, provenanceLabel, shortId, WARNING} from "../format.js";
import {content, mount} from "../view.js";

const RUNS_PAGE_SIZE = 100;

/** Shown under the method selector, so the chosen rule is never a mystery. */
const METHOD_FORMULAS = {
  majority_vote: "Most frequent hard class; ties resolve to the smallest class.",
  ordinal_mean: "Mean of the class indices, rounded half upward.",
  mean_probabilities: "Component-wise mean of the five probabilities; needs complete vectors.",
};

function storedPredictionRow(run) {
  return `<tr><td><a class="url detail-link" href="#article/${encodeURIComponent(run.article_id)}" title="${escapeHtml(run.canonical_url)}">${escapeHtml(run.canonical_url)}</a></td>
        <td><b>${escapeHtml(modelLabel(run))}</b><br><span class="muted">${escapeHtml(provenanceLabel(run.model_provenance))}</span></td>
        <td><span class="class-chip">${run.predicted_class}</span></td>${probabilityCells(run)}
        <td>${shortId(run.prediction_run_id)}</td></tr>`;
}

/** One row per model: each keeps its own verdict, they are never merged. */
function aggregationResults(payload) {
  if (!payload.models.length) {
    return `<div class="empty notice">No leakage-safe prediction is stored for this publisher, so no class can be read for it.</div>`;
  }
  return table(
    ["Model / fold", "Articles used", "Publisher class", "Ordinal mean", "Class counts"],
    payload.models.map(row => {
      const excluded = row.excluded_count
        ? `<br><span class="muted">${row.excluded_count} excluded</span>`
        : "";
      const verdict = row.result_class === null
        ? `<span class="muted">${escapeHtml(row.unavailable_reason || "Not available")}</span>`
        : `<span class="class-chip">Class ${row.result_class}</span>`;
      const counts = Object.entries(row.class_counts)
        .map(([cls, n]) => `${cls}:${n}`).join("  ");
      return `<tr><td><b>${escapeHtml(modelLabel(row))}</b><br><span class="muted">${escapeHtml(provenanceLabel(row.provenance))}</span></td>
        <td>${row.used_count} of ${row.available_count}${excluded}</td>
        <td>${verdict}</td>
        <td class="mono">${row.ordinal_mean === null ? "—" : Number(row.ordinal_mean).toFixed(3)}</td>
        <td class="mono">${escapeHtml(counts)}</td></tr>`;
    }),
  );
}

export async function publisherDetailPage(id, params) {
  const offset = Number(params.get("offset") || 0);
  const [publisher, runs] = await Promise.all([
    api(`/api/v1/publishers/${encodeURIComponent(id)}`),
    api(`/api/v1/prediction-runs?publisher_id=${encodeURIComponent(id)}&limit=${RUNS_PAGE_SIZE}&offset=${offset}`),
  ]);

  mount("publisher", {
    hostname: escapeHtml(publisher.normalized_hostname),
    articleCount: publisher.article_count,
    runCount: publisher.run_count,
    modelCount: publisher.model_count,
    warning: WARNING,
    storedPredictions: table(
      ["Article", "Model / fold", "Class", "P(0)", "P(1)", "P(2)", "P(3)", "P(4)", "Run"],
      runs.items.map(storedPredictionRow),
    ) + pager(`publisher/${encodeURIComponent(id)}`, runs.page),
  });

  const methodField = content.querySelector("#aggregation-method");
  const formula = content.querySelector("#method-formula");
  const output = content.querySelector("#aggregation-results");
  const exclusionList = content.querySelector("#exclusion-list");
  const excludedIds = new Set();

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
    const excluded = [...excludedIds]
      .map(value => `&exclude=${encodeURIComponent(value)}`).join("");
    output.className = "loading";
    output.textContent = "Reading the article predictions…";
    try {
      const payload = await api(
        `/api/v1/publishers/${encodeURIComponent(id)}/aggregation?method=${encodeURIComponent(methodField.value)}${excluded}`
      );
      output.className = "";
      output.innerHTML = aggregationResults(payload);
      if (withArticles) renderExclusionList(payload.articles);
    } catch (error) {
      output.className = "";
      output.innerHTML = errorCard(error.message);
    }
  }

  methodField.addEventListener("change", () => {
    formula.textContent = METHOD_FORMULAS[methodField.value];
    refresh();
  });
  await refresh(true);
}
