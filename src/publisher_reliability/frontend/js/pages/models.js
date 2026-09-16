/** #models — the checkpoint inventory, the directory scan and the custom import. */

import {api} from "../api.js";
import {errorCard, table} from "../components.js";
import {escapeHtml, modelLabel, provenanceLabel, shortId, statusPill} from "../format.js";
import {waitForJob} from "../job-progress.js";
import {content, mount} from "../view.js";

/** Remembers that this browser session already triggered the first scan. */
const SCAN_STARTED_KEY = "prt-model-scan-started";

/**
 * Two tables: checkpoints that exist on disk and can classify new articles, and
 * the dataset identities that only explain imported predictions.
 */
function renderModelTables(items) {
  const local = items.filter(row => row.identity_kind === "local");
  const historical = items.filter(row => row.identity_kind === "historical");
  return `
    <section class="section-block"><h2>Local and imported models</h2>
      <p class="muted">Models marked Ready can classify new article URLs. Core .pt checkpoints are discovered in configured directories; custom Transformers are installed from the ZIP form above.</p>
      ${table(
        ["Checkpoint", "Provenance", "Digest", "Status", "Available", "Inference"],
        local.map(row => `<tr><td><b>${escapeHtml(modelLabel(row))}</b><br><span class="mono">${escapeHtml(row.artifact_locator)}</span></td>
          <td><span class="source-badge">${escapeHtml(provenanceLabel(row.provenance))}</span></td>
          <td>${shortId(row.artifact_sha256)}</td><td>${statusPill(row.status)}<br><span class="muted">${escapeHtml(row.status_detail)}</span></td>
          <td>${row.artifact_available ? "Yes" : "No"}</td><td>${row.runnable ? "Ready" : "Not yet runnable"}</td></tr>`)
      )}</section>
    <details class="section-block"><summary>Historical dataset model identities (${historical.length})</summary>
      <p class="muted">These identities make imported predictions reproducible. They are not local checkpoint files and are not offered blindly in Evaluate.</p>
      ${table(
        ["Family / fold", "Model identity", "Status", "Stored only"],
        historical.map(row => `<tr><td><b>${escapeHtml(modelLabel(row))}</b></td><td>${shortId(row.model_id)}</td>
          <td>${statusPill(row.status)}</td><td>Yes</td></tr>`)
      )}</details>`;
}

export async function modelsPage() {
  mount("models");
  const scanButton = content.querySelector("#scan");
  const scanState = content.querySelector("#scan-state");
  const tables = content.querySelector("#model-tables");

  async function loadInventory() {
    const data = await api("/api/v1/models");
    tables.className = "";
    tables.innerHTML = renderModelTables(data.items);
    return data.items;
  }

  async function runScan() {
    scanButton.disabled = true;
    scanState.textContent = "Scanning and validating configured model directories…";
    try {
      const submitted = await api("/api/v1/models/scan", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
      });
      const job = await waitForJob(submitted.job_id, scanState);
      const rejected = job.result.rejected?.length || 0;
      scanState.textContent = `${job.result.message}${rejected ? ` ${rejected} checkpoint(s) rejected.` : ""}`;
      await loadInventory();
    } catch (error) {
      scanState.innerHTML = errorCard(error.message);
    } finally {
      scanButton.disabled = false;
    }
  }

  async function uploadCustomModel(event) {
    event.preventDefault();
    const uploadButton = event.currentTarget.querySelector("button");
    uploadButton.disabled = true;
    scanState.textContent = "Uploading custom Transformer bundle…";
    try {
      const submitted = await api("/api/v1/models/upload", {
        method: "POST",
        body: new FormData(event.currentTarget),
      });
      const job = await waitForJob(submitted.job_id, scanState);
      scanState.textContent = job.result.message;
      event.currentTarget.reset();
      await loadInventory();
    } catch (error) {
      scanState.innerHTML = errorCard(error.message);
    } finally {
      uploadButton.disabled = false;
    }
  }

  scanButton.addEventListener("click", runScan);
  content.querySelector("#custom-model-upload").addEventListener("submit", uploadCustomModel);

  // An empty inventory usually just means nothing has been scanned yet, so scan
  // once per browser session instead of showing the user an empty page.
  const items = await loadInventory();
  if (!items.some(row => row.identity_kind === "local") && !sessionStorage.getItem(SCAN_STARTED_KEY)) {
    sessionStorage.setItem(SCAN_STARTED_KEY, "true");
    await runScan();
  } else {
    scanState.textContent = "Inventory loaded. Rescan after adding or removing checkpoint files.";
  }
}
