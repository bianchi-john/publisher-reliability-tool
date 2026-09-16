/** #jobs — the history of the background worker's queue. */

import {api} from "../api.js";
import {table} from "../components.js";
import {escapeHtml, shortId, statusPill} from "../format.js";
import {content, mount, replaceLoading} from "../view.js";

const PAGE_SIZE = 25;

/** Result column: the failure message, the payload, or just the job id. */
function resultCell(row) {
  if (row.error_message) return `<span class="error">${escapeHtml(row.error_message)}</span>`;
  if (row.status === "succeeded") return `<span class="mono">${escapeHtml(JSON.stringify(row.result))}</span>`;
  return shortId(row.job_id);
}

export async function jobsPage() {
  mount("jobs");
  // Refresh simply re-renders the whole page.
  content.querySelector("#refresh").addEventListener("click", jobsPage);

  const data = await api(`/api/v1/jobs?limit=${PAGE_SIZE}`);
  replaceLoading(table(
    ["Created", "Type", "Status", "Phase", "Progress", "Result"],
    data.items.map(row => `<tr><td>${escapeHtml(row.created_at)}</td><td>${escapeHtml(row.job_type)}</td>
      <td>${statusPill(row.status)}</td><td>${escapeHtml(row.phase || "—")}</td><td>${row.progress}%</td>
      <td>${resultCell(row)}</td></tr>`),
  ));
}
