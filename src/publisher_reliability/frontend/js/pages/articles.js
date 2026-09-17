/** #articles — the list of articles, filterable by where they came from. */

import {api} from "../api.js";
import {articleSourceBadges, errorCard, pager, table} from "../components.js";
import {escapeHtml, shortId} from "../format.js";
import {content, mount} from "../view.js";

const PAGE_SIZE = 25;
const EXPORT_FILENAME = "article-predictions.csv";

/** The exact phrase the user must type to confirm a bulk, irreversible delete. */
const CLEAR_CONFIRMATION_PHRASE = "DELETE";

function articleRow(row) {
  const rowClass = row.source_type === "user_evaluation" ? "user-article-row" : "dataset-article-row";
  return `<tr class="${rowClass}"><td><a class="url detail-link" href="#article/${encodeURIComponent(row.article_id)}" title="${escapeHtml(row.canonical_url)}">${escapeHtml(row.canonical_url)}</a>${shortId(row.article_id)}</td>
      <td>${articleSourceBadges(row)}</td>
      <td><a class="detail-link" href="#publisher/${encodeURIComponent(row.publisher_id)}">${escapeHtml(row.normalized_hostname)}</a></td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td><span class="class-chip">Class ${row.latest_predicted_class}</span></td></tr>`;
}

/**
 * Fetch the CSV export and hand it to the browser as a download.
 *
 * A plain `<a href>` did this before with a full navigation; a real `<button>` lets
 * this show a busy state and an inline error instead of leaving a failed request as
 * an unexplained blank browser tab.
 */
async function downloadExport(query) {
  const response = await fetch(`/api/v1/articles/export${query}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error?.message || `Export failed (${response.status})`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = EXPORT_FILENAME;
  link.click();
  URL.revokeObjectURL(url);
}

export async function articlesPage(_id, params) {
  const offset = Number(params.get("offset") || 0);
  const source = params.get("source") || "";
  const sourceQuery = source ? `&article_source=${encodeURIComponent(source)}` : "";
  const exportQuery = source ? `?article_source=${encodeURIComponent(source)}` : "";
  const pageBase = source ? `articles?source=${encodeURIComponent(source)}` : "articles";

  mount("articles", {
    allTab: source ? "" : "active",
    datasetTab: source === "dataset" ? "active" : "",
    userTab: source === "user_evaluation" ? "active" : "",
  });

  const notice = content.querySelector("#page-notice");
  // errorCard() already draws its own bordered box, so it replaces the notice
  // styling entirely instead of nesting inside it.
  const showError = (message) => { notice.hidden = false; notice.className = ""; notice.innerHTML = errorCard(message); };
  const showNotice = (html) => { notice.hidden = false; notice.className = "notice"; notice.innerHTML = html; };
  const hideNotice = () => { notice.hidden = true; notice.innerHTML = ""; };

  const list = content.querySelector("#article-list");

  /** Refresh just the table, so a notice shown above it survives the reload. */
  async function loadArticles() {
    list.className = "loading";
    list.textContent = "Loading articles…";
    const data = await api(`/api/v1/articles?limit=${PAGE_SIZE}&sort=url_asc&offset=${offset}${sourceQuery}`);
    list.className = "";
    list.innerHTML = table(
      ["Article URL", "Source", "Publisher", "Models", "Predictions", "Latest label"],
      data.items.map(articleRow),
    ) + pager(pageBase, data.page, data.items.length);
  }

  const exportButton = content.querySelector("#export");
  exportButton.addEventListener("click", async () => {
    exportButton.disabled = true;
    hideNotice();
    try {
      await downloadExport(exportQuery);
    } catch (error) {
      showError(error.message);
    } finally {
      exportButton.disabled = false;
    }
  });

  // --- Clear user data: a page-drawn confirmation box, not window.confirm()/prompt().
  // Embedded browser contexts (for example VS Code's built-in preview) can suppress
  // those native dialogs outright, silently returning no answer; a box built out of
  // ordinary page elements renders the same everywhere the rest of the page does.
  const clearButton = content.querySelector("#clear-user-data");
  const dialog = content.querySelector("#clear-confirm");
  const dialogInput = content.querySelector("#clear-confirm-input");
  const dialogHint = content.querySelector("#clear-confirm-hint");
  const dialogCancel = content.querySelector("#clear-confirm-cancel");
  const dialogSubmit = content.querySelector("#clear-confirm-submit");

  function openClearDialog() {
    dialog.hidden = false;
    dialogInput.value = "";
    dialogHint.className = "dialog-hint";
    dialogHint.textContent = "";
    dialogSubmit.disabled = true;
    dialogInput.focus();
  }

  function closeClearDialog() {
    dialog.hidden = true;
    clearButton.focus();
  }

  clearButton.addEventListener("click", openClearDialog);
  dialogCancel.addEventListener("click", closeClearDialog);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeClearDialog();
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeClearDialog();
  });
  dialogInput.addEventListener("input", () => {
    const typed = dialogInput.value;
    const matches = typed === CLEAR_CONFIRMATION_PHRASE;
    dialogSubmit.disabled = !matches;
    if (!typed) {
      // Nothing typed yet: neither a warning nor a confirmation has anything to say.
      dialogHint.className = "dialog-hint";
      dialogHint.textContent = "";
    } else if (matches) {
      dialogHint.className = "dialog-hint match";
      dialogHint.textContent = "Confirmed. Click “Delete permanently” to continue.";
    } else {
      dialogHint.className = "dialog-hint mismatch";
      dialogHint.textContent = `Doesn't match "${CLEAR_CONFIRMATION_PHRASE}" yet.`;
    }
  });

  dialogSubmit.addEventListener("click", async () => {
    const typed = dialogInput.value;
    if (typed !== CLEAR_CONFIRMATION_PHRASE) return;
    dialogSubmit.disabled = true;
    dialogCancel.disabled = true;
    try {
      const result = await api("/api/v1/user-data", {
        method: "DELETE",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({confirmation: typed}),
      });
      dialog.hidden = true;
      showNotice(
        `<b>${result.deleted_predictions}</b> local prediction(s) and ` +
        `<b>${result.deleted_saved_content}</b> saved article(s) were deleted.`
      );
      await loadArticles();
    } catch (error) {
      dialog.hidden = true;
      showError(error.message);
    } finally {
      dialogCancel.disabled = false;
    }
  });

  await loadArticles();
}
