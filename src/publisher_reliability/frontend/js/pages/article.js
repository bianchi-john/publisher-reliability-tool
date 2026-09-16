/** #article/<id> — every model prediction stored for one article. */

import {api} from "../api.js";
import {articleSourceBadges, probabilityCells, table} from "../components.js";
import {escapeHtml, modelLabel, originLabel, provenanceLabel, shortId, WARNING} from "../format.js";
import {mount} from "../view.js";

function predictionRow(run) {
  const originClass = run.origin === "local_inference" ? "user-source" : "dataset-source";
  return `<tr><td><b>${escapeHtml(modelLabel(run))}</b><br><span class="muted">${escapeHtml(provenanceLabel(run.model_provenance))}</span></td>
        <td><span class="class-chip">${run.predicted_class}</span></td>${probabilityCells(run)}
        <td><span class="source-badge ${originClass}">${escapeHtml(originLabel(run.origin))}</span></td><td>${shortId(run.prediction_run_id)}</td></tr>`;
}

export async function articleDetailPage(id) {
  const row = await api(`/api/v1/articles/${encodeURIComponent(id)}`);
  const userEvaluated = row.source_type === "user_evaluation";

  mount("article", {
    hostname: escapeHtml(row.normalized_hostname),
    canonicalUrl: escapeHtml(row.canonical_url),
    publisherId: encodeURIComponent(row.publisher_id),
    sourcePanelClass: userEvaluated ? "user-source-panel" : "dataset-source-panel",
    sourceBadges: articleSourceBadges(row),
    sourceSentence: userEvaluated
      ? "Created through a user evaluation"
      : "Originally represented in an imported dataset",
    datasetRunCount: row.dataset_run_count,
    localRunCount: row.local_run_count,
    modelCount: row.model_count,
    runCount: row.run_count,
    latestClass: row.latest_predicted_class,
    predictionTable: table(
      ["Model / fold", "Predicted class", "P(class 0)", "P(class 1)", "P(class 2)", "P(class 3)", "P(class 4)", "Origin", "Run"],
      row.runs.map(predictionRow),
    ),
    warning: WARNING,
  });
}
