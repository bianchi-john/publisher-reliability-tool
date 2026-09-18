/** #jobs — the history of the background worker's queue. */

import {api} from "../api.js";
import {errorCard, table} from "../components.js";
import {escapeHtml, shortId, statusPill} from "../format.js";
import {content, mount} from "../view.js";

const PAGE_SIZE = 25;

/** Result column: the failure message, the payload, or just the job id. */
function resultCell(row) {
  if (row.error_message) return `<span class="error">${escapeHtml(row.error_message)}</span>`;
  if (row.status === "succeeded") return `<span class="mono">${escapeHtml(JSON.stringify(row.result))}</span>`;
  return shortId(row.job_id);
}

export async function jobsPage() {
  mount("jobs");

  const notice = content.querySelector("#page-notice");
  const showError = (message) => { notice.hidden = false; notice.className = ""; notice.innerHTML = errorCard(message); };
  const showNotice = (html) => { notice.hidden = false; notice.className = "notice"; notice.innerHTML = html; };
  const hideNotice = () => { notice.hidden = true; notice.innerHTML = ""; };

  const list = content.querySelector("#job-list");

  /** Refresh just the table, so a notice shown above it survives the reload. */
  async function loadJobs() {
    list.className = "loading";
    list.textContent = "Loading jobs…";
    const data = await api(`/api/v1/jobs?limit=${PAGE_SIZE}`);
    list.className = "";
    list.innerHTML = table(
      ["Created", "Type", "Status", "Phase", "Progress", "Result"],
      data.items.map(row => `<tr><td>${escapeHtml(row.created_at)}</td><td>${escapeHtml(row.job_type)}</td>
      <td>${statusPill(row.status)}</td><td>${escapeHtml(row.phase || "—")}</td><td>${row.progress}%</td>
      <td>${resultCell(row)}</td></tr>`),
    );
  }

  content.querySelector("#refresh").addEventListener("click", async () => {
    hideNotice();
    await loadJobs();
  });


  await loadJobs();
}
