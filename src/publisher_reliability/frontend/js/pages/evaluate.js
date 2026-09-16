/**
 * #evaluate — classify one article URL.
 *
 * Typing a URL asks the backend which models may be used for it; models whose
 * training set contains that article are reported as blocked, never offered.
 */

import {api} from "../api.js";
import {articlePredictionResult, errorCard, probabilityCells, table} from "../components.js";
import {escapeHtml, modelLabel, provenanceLabel, WARNING} from "../format.js";
import {progressCard, waitForJob} from "../job-progress.js";
import {content, mount} from "../view.js";

/** Wait for the user to stop typing before asking the backend about the URL. */
const MODEL_LOOKUP_DEBOUNCE_MS = 350;
const RECENT_LIMIT = 25;

const IDLE_AVAILABILITY = "Models will be detected from stored predictions for this article.";

function recentRow(run) {
  return `<tr class="user-article-row">
            <td><a class="url detail-link" href="#article/${encodeURIComponent(run.article_id)}" title="${escapeHtml(run.canonical_url)}">${escapeHtml(run.canonical_url)}</a>
              <span class="source-badge user-source">User evaluation</span></td>
            <td><a class="detail-link" href="#publisher/${encodeURIComponent(run.publisher_id)}">${escapeHtml(run.normalized_hostname)}</a></td>
            <td><b>${escapeHtml(modelLabel(run))}</b><br><span class="muted">${escapeHtml(provenanceLabel(run.model_provenance))}</span></td>
            <td><span class="class-chip">Class ${run.predicted_class}</span></td>${probabilityCells(run)}
            <td>${escapeHtml(run.inference_completed_at || run.recorded_at)}</td></tr>`;
}

/** Redraw the table of predictions this user has produced locally. */
async function loadRecentArticleEvaluations() {
  const recent = await api(`/api/v1/prediction-runs?origin=local_inference&limit=${RECENT_LIMIT}`);
  const body = recent.items.length
    ? table(
      ["Article", "Publisher", "Model / fold", "Predicted label", "P(0)", "P(1)", "P(2)", "P(3)", "P(4)", "Created"],
      recent.items.map(recentRow),
    )
    : `<div class="empty notice">No user article evaluation has been completed yet.</div>`;
  content.querySelector("#recent-article-evaluations").outerHTML =
    `<div id="recent-article-evaluations">${body}</div>`;
}

/** One dropdown entry, saying what picking this model would actually do. */
function modelOption(row) {
  const operation = row.mode === "new_inference"
    ? "new local inference"
    : `${row.article_count} stored held-out article(s)`;
  return `<option value="${escapeHtml(row.model_id)}">${escapeHtml(modelLabel(row))} · ${escapeHtml(operation)} · ${escapeHtml(row.local_status.replaceAll("_", " "))}</option>`;
}

/** Name the models that were withheld because the article trained them. */
function blockedNote(availability) {
  const blocked = availability.blocked_training_models || [];
  return blocked.length
    ? `<span class="muted">Blocked to prevent training leakage: ${blocked.map(row => escapeHtml(modelLabel(row))).join(", ")}.</span>`
    : "";
}

export async function evaluatePage() {
  mount("evaluate", {warning: WARNING});

  const form = content.querySelector("#evaluation");
  const urlField = form.elements.url;
  const modelField = form.elements.model_id;
  const availability = content.querySelector("#model-availability");
  const submit = form.querySelector("button[type='submit'], button:not([type])");
  let timer;

  /** Nothing usable to offer: lock the form and explain why. */
  function disableModelChoice(message, asHtml = false) {
    modelField.disabled = true;
    submit.disabled = true;
    availability.hidden = false;
    availability.className = "notice";
    if (asHtml) availability.innerHTML = message; else availability.textContent = message;
  }

  async function refreshAvailable() {
    clearTimeout(timer);
    if (!urlField.validity.valid || !urlField.value) {
      modelField.innerHTML = `<option value="">Enter a valid URL first</option>`;
      disableModelChoice(IDLE_AVAILABILITY);
      return;
    }
    availability.hidden = false;
    availability.className = "notice";
    availability.textContent = "Detecting compatible stored predictions…";
    const query = new URLSearchParams({input_type: "article", url: urlField.value});
    try {
      const data = await api(`/api/v1/models/available?${query}`);
      const eligible = data.items.filter(row => row.eligible);
      modelField.innerHTML = eligible.length
        ? eligible.map(modelOption).join("")
        : `<option value="">No available model</option>`;
      modelField.disabled = !eligible.length;
      submit.disabled = !eligible.length;
      const note = blockedNote(data.availability);
      if (data.availability.code === "AVAILABLE") {
        // Nothing to say unless some models had to be withheld.
        availability.hidden = !note;
        availability.className = "notice";
        availability.innerHTML = note;
      } else {
        availability.hidden = false;
        availability.className = "notice notice-warning";
        availability.innerHTML = `<b>${escapeHtml(data.availability.message)}</b>${note ? `<br>${note}` : ""}`;
      }
    } catch (error) {
      disableModelChoice(errorCard(error.message), true);
    }
  }

  urlField.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(refreshAvailable, MODEL_LOOKUP_DEBOUNCE_MS);
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const data = new FormData(form);
    const body = {
      input: {type: "article", url: data.get("url")},
      model_id: data.get("model_id"),
      prediction_action: "reuse",
      content_retention: "discard",
    };
    const output = content.querySelector("#evaluation-result");
    output.innerHTML = progressCard("submitting evaluation", 0);
    try {
      const job = await api("/api/v1/evaluation-jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      const completed = await waitForJob(job.job_id, output);
      output.innerHTML = articlePredictionResult(completed.result);
      await loadRecentArticleEvaluations();
    } catch (error) { output.innerHTML = errorCard(error.message); }
  });

  await loadRecentArticleEvaluations();
}
