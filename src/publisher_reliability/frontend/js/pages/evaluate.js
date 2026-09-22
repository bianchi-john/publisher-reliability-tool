/**
 * #evaluate — classify one article URL.
 *
 * Typing a URL asks the backend which models may be used for it; models whose
 * training set contains that article are reported as blocked, never offered.
 * That lookup is about models only. Whether the link is an article at all is
 * decided by the evaluation itself, once the reader presses the button.
 */

import {api} from "../api.js";
import {articlePredictionResult, errorCard} from "../components.js";
import {escapeHtml, modelLabel} from "../format.js";
import {progressCard, waitForJob} from "../job-progress.js";
import {content, mount} from "../view.js";

/** Wait for the user to stop typing before asking the backend about the URL. */
const MODEL_LOOKUP_DEBOUNCE_MS = 350;

const IDLE_AVAILABILITY = "Models will be detected from stored predictions for this article.";

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
  mount("evaluate", {});

  const form = content.querySelector("#evaluation");
  const urlField = form.elements.url;
  const modelField = form.elements.model_id;
  const availability = content.querySelector("#model-availability");
  const submit = form.querySelector("button[type='submit'], button:not([type])");
  let timer;
  // The debounce spaces lookups out but cannot stop two from overlapping once the
  // user resumes typing while one is still in flight. Responses may then arrive out
  // of order, and the slower, older one would describe a URL the field no longer
  // holds. Each lookup takes a ticket and only the newest is allowed to draw.
  let latestLookup = 0;

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
    const ticket = ++latestLookup;
    // The only test applied while typing is the browser's own check that the box
    // holds something URL-shaped. Whether the address is a homepage, or leads to
    // a page that is not an article at all, is settled when the evaluation is
    // started: those answers cost a request, and the reader has not asked for
    // one yet.
    if (!urlField.validity.valid || !urlField.value) {
      modelField.innerHTML = `<option value="">Enter a URL first</option>`;
      disableModelChoice(IDLE_AVAILABILITY);
      return;
    }
    availability.hidden = false;
    availability.className = "notice";
    availability.textContent = "Detecting compatible stored predictions…";
    const query = new URLSearchParams({url: urlField.value});
    try {
      const data = await api(`/api/v1/models/available?${query}`);
      if (ticket !== latestLookup) return;
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
      if (ticket !== latestLookup) return;
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
    } catch (error) { output.innerHTML = errorCard(error.message); }
  });
}
