/** Small HTML fragments reused across pages. */

import {escapeHtml, modelLabel, provenanceLabel, shortId} from "./format.js";
import {render} from "./templates.js";

/** Inline error message, announced to screen readers. */
export const errorCard = (message) =>
  `<div class="error-card" role="alert"><span class="error-icon" aria-hidden="true">!</span><span>${escapeHtml(message)}</span></div>`;

/**
 * Wrap pre-rendered `<tr>` strings in a table, or show an empty-state notice.
 * Headers are inserted verbatim so they may contain markup.
 *
 * `className` is for tables whose rows behave differently from the rest, such as a
 * list where every row opens a page of its own. It is optional so that a table
 * without such behaviour is not made to declare that it has none.
 */
export function table(headers, rows, className = "") {
  if (!rows.length) return `<div class="empty notice">No records match this view.</div>`;
  const named = className ? ` class="${className}"` : "";
  return `<div class="table-wrap"><table${named}><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.join("")}</tbody></table></div>`;
}

/**
 * Previous/next links for an offset-paginated list.
 * `base` is the hash route to link back to, with its own query string if any.
 *
 * `rowCount` is how many rows this page actually returned. It is needed because the
 * API reports the requested `limit`, not the size of the page it answered with, so a
 * partial last page would otherwise be labelled with rows that are not on screen.
 */
export function pager(base, page, rowCount = page.limit) {
  const separator = base.includes("?") ? "&" : "?";
  const previous = page.offset > 0
    ? `<a class="button secondary" href="#${base}${separator}offset=${Math.max(0, page.offset - page.limit)}">Previous</a>`
    : "";
  const next = page.next_offset !== null
    ? `<a class="button secondary" href="#${base}${separator}offset=${page.next_offset}">Next</a>`
    : "";
  const range = rowCount > 0
    ? `Rows ${page.offset + 1}–${page.offset + rowCount}`
    : "No rows";
  return previous || next ? `<div class="pager">${previous}<span class="muted">${range}</span>${next}</div>` : "";
}

/**
 * The five per-class probability cells of a prediction row.
 * Some imported dataset predictions store only the hard class.
 */
export function probabilityCells(run) {
  if (!run.probabilities) {
    return `<td colspan="5"><span class="muted">Not supplied by this model in the dataset</span></td>`;
  }
  return run.probabilities.map(value => `<td class="mono probability">${(Number(value) * 100).toFixed(2)}%</td>`).join("");
}

/** Badges telling a dataset article apart from one the user classified locally. */
export function articleSourceBadges(row) {
  const primary = row.source_type === "user_evaluation"
    ? `<span class="source-badge user-source">User evaluated</span>`
    : `<span class="source-badge dataset-source">Dataset article</span>`;
  const local = row.source_type === "dataset" && row.has_user_evaluation
    ? `<span class="source-badge user-source">Also evaluated by user</span>`
    : "";
  return `<span class="source-badges">${primary}${local}</span>`;
}

/** One horizontal bar per class, with the predicted one highlighted. */
function probabilityBars(result) {
  return result.probabilities.map((value, index) => {
    const percent = Number(value) * 100;
    const selected = index === Number(result.predicted_class);
    return `<div class="probability-result ${selected ? "predicted" : ""}">
      <div class="probability-result-label"><span>Class ${index}${selected ? " · predicted" : ""}</span>
        <b>${percent.toFixed(2)}%</b></div>
      <div class="probability-track"><span style="width:${Math.max(0, Math.min(100, percent))}%"></span></div>
      <div class="mono">${Number(value).toFixed(8)}</div>
    </div>`;
  }).join("");
}

/** The result card shown on Evaluate once a classification completes. */
export function articlePredictionResult(result) {
  return render("prediction-result", {
    predictedClass: result.predicted_class,
    sourceClass: result.origin === "local_inference" ? "user-source" : "dataset-source",
    sourceText: escapeHtml(result.reused ? "Stored prediction reused" : "New user evaluation"),
    modelLabel: escapeHtml(modelLabel(result)),
    provenance: escapeHtml(provenanceLabel(result.model_provenance)),
    probabilityBars: probabilityBars(result),
    articleId: encodeURIComponent(result.article_id),
    runId: shortId(result.prediction_run_id),
  });
}
