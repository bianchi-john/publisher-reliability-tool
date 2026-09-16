const content = document.querySelector("#content");
const stateBadge = document.querySelector("#system-state");
const systemPopover = document.querySelector("#system-popover");
const warning = "Predictions are estimates, not fact checks. Softmax values are not necessarily calibrated confidence.";
let routeController = null;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const shortId = (value) => `<span class="mono" title="${escapeHtml(value)}">${escapeHtml(String(value).slice(0, 12))}…</span>`;
const statusPill = (value) => `<span class="pill ${escapeHtml(value)}">${escapeHtml(value).replaceAll("_", " ")}</span>`;
const pageHead = (eyebrow, title, intro, action = "") => `
  <header class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1>
  <p class="intro">${intro}</p></div>${action}</header>`;
const errorCard = (message) => `<div class="error-card" role="alert"><span class="error-icon" aria-hidden="true">!</span><span>${escapeHtml(message)}</span></div>`;
const humanizePhase = (value) => {
  const text = String(value ?? "").replaceAll("_", " ").trim() || "working";
  return escapeHtml(text.charAt(0).toUpperCase() + text.slice(1));
};
const progressCard = (phase, percent) => {
  const clamped = Math.max(0, Math.min(100, Number(percent) || 0));
  return `<div class="progress-card" aria-live="polite">
    <div class="progress-message"><span>${humanizePhase(phase)}…</span><b>${clamped}%</b></div>
    <div class="progress-track"><span style="width:${clamped}%"></span></div>
  </div>`;
};
const modelLabel = (row) => row.display_name || row.model_display_name || `${String(row.family).toUpperCase()} · fold ${row.fold_id}`;
const provenanceLabel = (value) => ({
  paper_official: "Paper original",
  user_custom: "User custom",
  paper_dataset: "Dataset identity",
  local_checkpoint: "Local checkpoint",
})[value] || value || "Unknown provenance";
const originLabel = (origin) => ({
  bundled_import: "Original dataset",
  user_import: "Imported dataset",
  local_inference: "User evaluation",
})[origin] || origin;

function articleSourceBadges(row) {
  const primary = row.source_type === "user_evaluation"
    ? `<span class="source-badge user-source">User evaluated</span>`
    : `<span class="source-badge dataset-source">Dataset article</span>`;
  const local = row.source_type === "dataset" && row.has_user_evaluation
    ? `<span class="source-badge user-source">Also evaluated by user</span>`
    : "";
  return `<span class="source-badges">${primary}${local}</span>`;
}

async function api(path, options = {}) {
  const requestOptions = {...options};
  if (!requestOptions.signal && routeController) {
    requestOptions.signal = routeController.signal;
  }
  const response = await fetch(path, requestOptions);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error?.message || `Request failed (${response.status})`);
  return body;
}

function table(headers, rows) {
  if (!rows.length) return `<div class="empty notice">No records match this view.</div>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.join("")}</tbody></table></div>`;
}

function parseLocation() {
  const raw = location.hash.slice(1) || "evaluate";
  const [path, query = ""] = raw.split("?", 2);
  const parts = path.split("/").filter(Boolean);
  return {page: parts[0] || "evaluate", id: parts[1] || "", params: new URLSearchParams(query)};
}

function probabilityCells(run) {
  if (!run.probabilities) {
    return `<td colspan="5"><span class="muted">Not supplied by this model in the dataset</span></td>`;
  }
  return run.probabilities.map(value => `<td class="mono probability">${(Number(value) * 100).toFixed(2)}%</td>`).join("");
}

function articlePredictionResult(result) {
  const sourceText = result.reused
    ? "Stored prediction reused"
    : "New user evaluation";
  const sourceClass = result.origin === "local_inference" ? "user-source" : "dataset-source";
  return `<section class="evaluation-result-card" aria-labelledby="prediction-result-title">
    <div class="result-heading">
      <div>
        <div class="eyebrow">Evaluation completed</div>
        <h2 id="prediction-result-title">Predicted label</h2>
      </div>
      <div class="predicted-label">Class ${result.predicted_class}</div>
    </div>
    <div class="result-meta">
      <span class="source-badge ${sourceClass}">${escapeHtml(sourceText)}</span>
      <span><b>Model:</b> ${escapeHtml(modelLabel(result))}</span>
      <span class="source-badge">${escapeHtml(provenanceLabel(result.model_provenance))}</span>
    </div>
    <h3>Probabilities for every class</h3>
    <div class="probability-results">
      ${result.probabilities.map((value, index) => {
        const percent = Number(value) * 100;
        const selected = index === Number(result.predicted_class);
        return `<div class="probability-result ${selected ? "predicted" : ""}">
          <div class="probability-result-label"><span>Class ${index}${selected ? " · predicted" : ""}</span>
            <b>${percent.toFixed(2)}%</b></div>
          <div class="probability-track"><span style="width:${Math.max(0, Math.min(100, percent))}%"></span></div>
          <div class="mono">${Number(value).toFixed(8)}</div>
        </div>`;
      }).join("")}
    </div>
    <div class="result-actions">
      <a class="button secondary" href="#article/${encodeURIComponent(result.article_id)}">Open complete prediction history</a>
      <span class="muted">Run ${shortId(result.prediction_run_id)}</span>
    </div>
    <p class="warning">${warning}</p>
  </section>`;
}

function pager(base, page) {
  const separator = base.includes("?") ? "&" : "?";
  const previous = page.offset > 0
    ? `<a class="button secondary" href="#${base}${separator}offset=${Math.max(0, page.offset - page.limit)}">Previous</a>`
    : "";
  const next = page.next_offset !== null
    ? `<a class="button secondary" href="#${base}${separator}offset=${page.next_offset}">Next</a>`
    : "";
  return previous || next ? `<div class="pager">${previous}<span class="muted">Rows ${page.offset + 1}–${page.offset + page.limit}</span>${next}</div>` : "";
}

async function refreshSystemBadge() {
  try {
    const status = await api("/api/v1/status");
    stateBadge.textContent = status.offline ? "Ready · offline" : "Ready · local";
    return status;
  } catch (error) {
    stateBadge.textContent = "Status unavailable";
    return null;
  }
}

async function loadSystemPopover() {
  systemPopover.innerHTML = `<div class="loading">Loading overview…</div>`;
  try {
    const status = await api("/api/v1/status");
    const c = status.ledger_counts;
    const d = status.derived_counts;
    systemPopover.innerHTML = `
      <div class="popover-section">
        <div class="popover-row"><span>Articles</span><b>${Number(d.articles).toLocaleString()}</b></div>
        <div class="popover-row"><span>Stored predictions</span><b>${Number(d.historical_predictions).toLocaleString()}</b></div>
        <div class="popover-row"><span>Publishers</span><b>${Number(d.publishers).toLocaleString()}</b></div>
        <div class="popover-row"><span>Model identities</span><b>${Number(c.models).toLocaleString()}</b></div>
      </div>
      <div class="popover-section">
        <div class="popover-row"><span>Device</span><b>${escapeHtml(status.device)}</b></div>
        <div class="popover-row"><span>Schema</span><b>${escapeHtml(status.schema_version)}</b></div>
        <div class="popover-row"><span>Version</span><b>${escapeHtml(status.application_version)}</b></div>
      </div>
      <a class="popover-link" href="#models">Manage models →</a>`;
  } catch (error) {
    systemPopover.innerHTML = errorCard(error.message);
  }
}

function closeSystemPopover() {
  if (systemPopover.hidden) return;
  systemPopover.hidden = true;
  stateBadge.setAttribute("aria-expanded", "false");
}

async function toggleSystemPopover() {
  const opening = systemPopover.hidden;
  systemPopover.hidden = !opening;
  stateBadge.setAttribute("aria-expanded", String(opening));
  if (opening) await loadSystemPopover();
}

stateBadge.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleSystemPopover();
});
document.addEventListener("click", (event) => {
  if (!systemPopover.hidden && !systemPopover.contains(event.target) && event.target !== stateBadge) {
    closeSystemPopover();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !systemPopover.hidden) {
    closeSystemPopover();
    stateBadge.focus();
  }
});
window.addEventListener("hashchange", closeSystemPopover);

async function articles(_id, params) {
  const offset = Number(params.get("offset") || 0);
  const source = params.get("source") || "";
  const sourceQuery = source ? `&article_source=${encodeURIComponent(source)}` : "";
  const pageBase = source ? `articles?source=${encodeURIComponent(source)}` : "articles";
  content.innerHTML = pageHead("Prediction history", "Articles & predictions",
    "Dataset articles and articles classified by the user are identified separately. Open one to inspect every model output and probability.",
    `<a class="button secondary" href="/api/v1/articles/export${source ? `?article_source=${encodeURIComponent(source)}` : ""}">Export predictions CSV</a>`) + `
    <div class="source-tabs" aria-label="Filter articles by source">
      <a class="${source ? "" : "active"}" href="#articles">All articles</a>
      <a class="${source === "dataset" ? "active" : ""}" href="#articles?source=dataset">Dataset articles</a>
      <a class="${source === "user_evaluation" ? "active" : ""}" href="#articles?source=user_evaluation">User-evaluated articles</a>
    </div>
    <div class="source-legend">
      <span><span class="source-dot dataset-source"></span><b>Dataset article:</b> at least one imported prediction.</span>
      <span><span class="source-dot user-source"></span><b>User evaluated:</b> a new article classified locally through Evaluate.</span>
    </div>
    <div class="loading">Loading articles…</div>`;
  const data = await api(`/api/v1/articles?limit=25&sort=url_asc&offset=${offset}${sourceQuery}`);
  content.querySelector(".loading").outerHTML = table(
    ["Article URL", "Source", "Publisher", "Models", "Predictions", "Latest label"],
    data.items.map(row => `<tr class="${row.source_type === "user_evaluation" ? "user-article-row" : "dataset-article-row"}"><td><a class="url detail-link" href="#article/${encodeURIComponent(row.article_id)}" title="${escapeHtml(row.canonical_url)}">${escapeHtml(row.canonical_url)}</a>${shortId(row.article_id)}</td>
      <td>${articleSourceBadges(row)}</td>
      <td><a class="detail-link" href="#publisher/${encodeURIComponent(row.publisher_id)}">${escapeHtml(row.normalized_hostname)}</a></td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td><span class="class-chip">Class ${row.latest_predicted_class}</span></td></tr>`)
  ) + pager(pageBase, data.page);
}

async function articleDetail(id) {
  const row = await api(`/api/v1/articles/${encodeURIComponent(id)}`);
  content.innerHTML = pageHead("Article prediction history", row.normalized_hostname,
    row.canonical_url,
    `<a class="button secondary" href="#publisher/${encodeURIComponent(row.publisher_id)}">Publisher class</a>`) + `
    <div class="article-source-banner ${row.source_type === "user_evaluation" ? "user-source-panel" : "dataset-source-panel"}">
      ${articleSourceBadges(row)}
      <b>${row.source_type === "user_evaluation" ? "Created through a user evaluation" : "Originally represented in an imported dataset"}</b>
      <span>${row.dataset_run_count} imported prediction(s) · ${row.local_run_count} local user evaluation(s)</span>
    </div>
    <div class="grid detail-metrics">
      <section class="card"><div class="muted">Models</div><div class="metric">${row.model_count}</div></section>
      <section class="card"><div class="muted">Stored predictions</div><div class="metric">${row.run_count}</div></section>
      <section class="card"><div class="muted">Latest class</div><div class="metric">${row.latest_predicted_class}</div></section>
    </div>
    <section class="section-block"><h2>Every model prediction</h2>
    ${table(
      ["Model / fold", "Predicted class", "P(class 0)", "P(class 1)", "P(class 2)", "P(class 3)", "P(class 4)", "Origin", "Run"],
      row.runs.map(run => `<tr><td><b>${escapeHtml(modelLabel(run))}</b><br><span class="muted">${escapeHtml(provenanceLabel(run.model_provenance))}</span></td>
        <td><span class="class-chip">${run.predicted_class}</span></td>${probabilityCells(run)}
        <td><span class="source-badge ${run.origin === "local_inference" ? "user-source" : "dataset-source"}">${escapeHtml(originLabel(run.origin))}</span></td><td>${shortId(run.prediction_run_id)}</td></tr>`)
    )}</section><p class="warning">${warning}</p>`;
}

async function publishers(_id, params) {
  const offset = Number(params.get("offset") || 0);
  content.innerHTML = pageHead("Publisher reliability", "Publishers",
    "A publisher's class is read from the articles already classified. Open one to choose how its article verdicts are counted.") + `<div class="loading">Loading publishers…</div>`;
  const data = await api(`/api/v1/publishers?limit=25&offset=${offset}`);
  content.querySelector(".loading").outerHTML = table(
    ["Publisher", "Articles", "Models", "Predictions", "With probabilities"],
    data.items.map(row => `<tr><td><a class="detail-link" href="#publisher/${encodeURIComponent(row.publisher_id)}"><b>${escapeHtml(row.normalized_hostname)}</b></a><br>${shortId(row.publisher_id)}</td>
      <td>${row.article_count}</td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td>${row.probability_run_count}</td></tr>`)
  ) + pager("publishers", data.page);
}

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
    })
  );
}

async function publisherDetail(id, params) {
  const offset = Number(params.get("offset") || 0);
  const [publisher, runs] = await Promise.all([
    api(`/api/v1/publishers/${encodeURIComponent(id)}`),
    api(`/api/v1/prediction-runs?publisher_id=${encodeURIComponent(id)}&limit=100&offset=${offset}`),
  ]);

  content.innerHTML = pageHead("Publisher reliability", publisher.normalized_hostname,
    "This class is derived from the article predictions below, not stored. Change how the verdicts are counted, or leave articles out, and it is recomputed.",
    `<a class="button secondary" href="#publishers">Back to publishers</a>`) + `
    <div class="grid detail-metrics">
      <section class="card"><div class="muted">Articles</div><div class="metric">${publisher.article_count}</div></section>
      <section class="card"><div class="muted">Stored predictions</div><div class="metric">${publisher.run_count}</div></section>
      <section class="card"><div class="muted">Models</div><div class="metric">${publisher.model_count}</div></section>
    </div>
    <section class="card full">
      <h2>Publisher class</h2>
      <div class="row">
        <label>How article verdicts are counted<select id="aggregation-method">
          <option value="majority_vote">Majority vote</option>
          <option value="ordinal_mean">Ordinal mean</option>
          <option value="mean_probabilities">Mean probabilities</option>
        </select>
          <small id="method-formula">Most frequent hard class; ties resolve to the smallest class.</small></label>
      </div>
      <div id="aggregation-results" class="loading">Reading the article predictions…</div>
      <p class="warning">${warning}</p>
    </section>
    <section class="section-block"><h2>Articles counted</h2>
      <p class="muted">Every article of this publisher with a leakage-safe prediction is counted. Clear a checkbox to leave it out; each model is recounted over what remains.</p>
      <div id="exclusion-list" class="exclusion-list loading">Loading articles…</div>
    </section>
    <section class="section-block"><h2>Stored predictions</h2>
    ${table(
      ["Article", "Model / fold", "Class", "P(0)", "P(1)", "P(2)", "P(3)", "P(4)", "Run"],
      runs.items.map(run => `<tr><td><a class="url detail-link" href="#article/${encodeURIComponent(run.article_id)}" title="${escapeHtml(run.canonical_url)}">${escapeHtml(run.canonical_url)}</a></td>
        <td><b>${escapeHtml(modelLabel(run))}</b><br><span class="muted">${escapeHtml(provenanceLabel(run.model_provenance))}</span></td>
        <td><span class="class-chip">${run.predicted_class}</span></td>${probabilityCells(run)}
        <td>${shortId(run.prediction_run_id)}</td></tr>`)
    )}${pager(`publisher/${encodeURIComponent(id)}`, runs.page)}</section>`;

  const methodField = document.querySelector("#aggregation-method");
  const formula = document.querySelector("#method-formula");
  const output = document.querySelector("#aggregation-results");
  const formulas = {
    majority_vote: "Most frequent hard class; ties resolve to the smallest class.",
    ordinal_mean: "Mean of the class indices, rounded half upward.",
    mean_probabilities: "Component-wise mean of the five probabilities; needs complete vectors.",
  };

  const exclusionList = document.querySelector("#exclusion-list");
  const excludedIds = new Set();

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
    formula.textContent = formulas[methodField.value];
    refresh();
  });
  await refresh(true);
}

async function waitForJob(jobId, output) {
  const deadline = Date.now() + 480000;
  while (Date.now() < deadline) {
    const job = await api(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
    output.innerHTML = progressCard(job.phase || job.status, job.progress);
    if (job.status === "succeeded") return job;
    if (job.status === "failed") throw new Error(job.error_message || "Model scan failed.");
    await new Promise(resolve => setTimeout(resolve, 700));
  }
  throw new Error("This job is still running; inspect it on the Jobs page.");
}

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

async function models() {
  content.innerHTML = pageHead("Checkpoint inventory", "Models",
    "Add BERT or RoBERTa checkpoints, or import a compatible user-created five-class Transformer. Their provenance remains distinct in every prediction.",
    `<button id="scan">Rescan model directories</button>`) + `
    <section class="card full"><h2>Import a custom five-class Transformer</h2>
      <ol>
        <li>Export the complete classifier with safe serialization (<span class="mono">safetensors</span>) together with its tokenizer.</li>
        <li>Add <span class="mono">prt-model.json</span> to that same folder, then compress the complete folder as one <span class="mono">.zip</span>.</li>
        <li>The model must output exactly five logits in class order 0–4. Imported predictions are marked <b>User custom</b>.</li>
      </ol>
      <details><summary>Manifest example</summary>
        <p class="muted">Required alongside the manifest: config.json, model.safetensors, tokenizer_config.json and the tokenizer resources. Executable custom code and pickle checkpoints are rejected.</p>
        <pre class="mono">${escapeHtml(`{
  "schema_version": 1,
  "display_name": "My custom encoder classifier",
  "family": "custom_encoder_experiment",
  "fold_id": 1,
  "class_order": [0, 1, 2, 3, 4],
  "max_tokens": 256,
  "padding_policy": "fixed_max_length",
  "training_data": {"kind": "five_fold", "held_out_fold": 1}
}`)}</pre>
      </details>
      <form id="custom-model-upload"><div class="row">
        <label>Choose the complete custom-model ZIP<input required name="file" type="file" accept=".zip,application/zip"></label>
        <button>Validate and import</button>
      </div></form>
      <p class="notice">Support for the paper's larger decoder checkpoints (Llama 3 8B, Mistral 24B) is still under development and not available in this release. They need a CUDA GPU and several gigabytes per fold; BERT and RoBERTa run on CPU and report comparable accuracy.</p>
    </section>
    <div id="scan-state" class="notice" aria-live="polite">Loading model inventory…</div>
    <div id="model-tables" class="loading">Loading models…</div>`;
  const scanButton = document.querySelector("#scan");
  const scanState = document.querySelector("#scan-state");
  const tables = document.querySelector("#model-tables");

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

  scanButton.addEventListener("click", runScan);
  document.querySelector("#custom-model-upload").addEventListener("submit", async event => {
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
  });
  const items = await loadInventory();
  if (!items.some(row => row.identity_kind === "local") && !sessionStorage.getItem("prt-model-scan-started")) {
    sessionStorage.setItem("prt-model-scan-started", "true");
    await runScan();
  } else {
    scanState.textContent = "Inventory loaded. Rescan after adding or removing checkpoint files.";
  }
}

async function jobsPage() {
  content.innerHTML = pageHead("Persisted operations", "Jobs",
    "Model scans, dataset imports and aggregations run through one FIFO worker.",
    `<button class="secondary" id="refresh">Refresh</button>`) + `<div class="loading">Loading jobs…</div>`;
  document.querySelector("#refresh").addEventListener("click", jobsPage);
  const data = await api("/api/v1/jobs?limit=25");
  content.querySelector(".loading").outerHTML = table(
    ["Created", "Type", "Status", "Phase", "Progress", "Result"],
    data.items.map(row => `<tr><td>${escapeHtml(row.created_at)}</td><td>${escapeHtml(row.job_type)}</td>
      <td>${statusPill(row.status)}</td><td>${escapeHtml(row.phase || "—")}</td><td>${row.progress}%</td>
      <td>${row.error_message ? `<span class="error">${escapeHtml(row.error_message)}</span>` : row.status === "succeeded" ? `<span class="mono">${escapeHtml(JSON.stringify(row.result))}</span>` : shortId(row.job_id)}</td></tr>`)
  );
}

async function evaluate() {
  content.innerHTML = pageHead("Article classification", "Evaluate",
    "Classify one article. A publisher's class is not created here: it is read from the articles already classified, under Publishers.") + `
    <section class="card full"><form id="evaluation">
      <div class="row">
        <label class="grow">Article URL<input required name="url" type="url" placeholder="https://publisher.example/article"></label>
      </div>
      <div class="row evaluation-options">
        <label>Available model<select required disabled name="model_id"><option value="">Enter a valid URL first</option></select></label>
      </div>
      <div id="model-availability" class="notice" aria-live="polite">Models will be detected from stored predictions for this article.</div>
      <div class="row evaluation-actions"><button disabled>Start evaluation</button></div>
    </form><div id="evaluation-result" aria-live="polite"></div></section>
    <section class="section-block"><h2>Recent user article evaluations</h2>
      <p class="muted">New local predictions remain visible here after a refresh. Open an article for its complete model history, or a publisher to read its class.</p>
      <div id="recent-article-evaluations" class="loading">Loading user evaluations…</div>
    </section>
    <p class="warning">${warning}</p>`;

  const form = document.querySelector("#evaluation");
  const urlField = form.elements.url;
  const modelField = form.elements.model_id;
  const availability = document.querySelector("#model-availability");
  const submit = form.querySelector("button[type='submit'], button:not([type])");
  let timer;

  async function loadRecentArticleEvaluations() {
    const recent = await api("/api/v1/prediction-runs?origin=local_inference&limit=25");
    document.querySelector("#recent-article-evaluations").outerHTML = `<div id="recent-article-evaluations">${
      recent.items.length
        ? table(
          ["Article", "Publisher", "Model / fold", "Predicted label", "P(0)", "P(1)", "P(2)", "P(3)", "P(4)", "Created"],
          recent.items.map(run => `<tr class="user-article-row">
            <td><a class="url detail-link" href="#article/${encodeURIComponent(run.article_id)}" title="${escapeHtml(run.canonical_url)}">${escapeHtml(run.canonical_url)}</a>
              <span class="source-badge user-source">User evaluation</span></td>
            <td><a class="detail-link" href="#publisher/${encodeURIComponent(run.publisher_id)}">${escapeHtml(run.normalized_hostname)}</a></td>
            <td><b>${escapeHtml(modelLabel(run))}</b><br><span class="muted">${escapeHtml(provenanceLabel(run.model_provenance))}</span></td>
            <td><span class="class-chip">Class ${run.predicted_class}</span></td>${probabilityCells(run)}
            <td>${escapeHtml(run.inference_completed_at || run.recorded_at)}</td></tr>`)
        )
        : `<div class="empty notice">No user article evaluation has been completed yet.</div>`
    }</div>`;
  }

  async function refreshAvailable() {
    clearTimeout(timer);
    if (!urlField.validity.valid || !urlField.value) {
      modelField.innerHTML = `<option value="">Enter a valid URL first</option>`;
      modelField.disabled = true;
      submit.disabled = true;
      availability.hidden = false;
      availability.className = "notice";
      availability.textContent = "Models will be detected from stored predictions for this article.";
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
        ? eligible.map(row => {
          const operation = row.mode === "new_inference"
            ? "new local inference"
            : `${row.article_count} stored held-out article(s)`;
          return `<option value="${escapeHtml(row.model_id)}">${escapeHtml(modelLabel(row))} · ${escapeHtml(operation)} · ${escapeHtml(row.local_status.replaceAll("_", " "))}</option>`;
        }).join("")
        : `<option value="">No available model</option>`;
      modelField.disabled = !eligible.length;
      submit.disabled = !eligible.length;
      const blocked = data.availability.blocked_training_models || [];
      const blockedNote = blocked.length
        ? `<span class="muted">Blocked to prevent training leakage: ${blocked.map(row => escapeHtml(modelLabel(row))).join(", ")}.</span>`
        : "";
      if (data.availability.code === "AVAILABLE") {
        availability.hidden = !blockedNote;
        availability.className = "notice";
        availability.innerHTML = blockedNote;
      } else {
        availability.hidden = false;
        availability.className = "notice notice-warning";
        availability.innerHTML = `<b>${escapeHtml(data.availability.message)}</b>${blockedNote ? `<br>${blockedNote}` : ""}`;
      }
    } catch (error) {
      modelField.disabled = true;
      submit.disabled = true;
      availability.hidden = false;
      availability.className = "notice";
      availability.innerHTML = errorCard(error.message);
    }
  }

  function scheduleRefresh() {
    clearTimeout(timer);
    timer = setTimeout(refreshAvailable, 350);
  }
  urlField.addEventListener("input", scheduleRefresh);

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const data = new FormData(form);
    const body = {
      input: {type: "article", url: data.get("url")},
      model_id: data.get("model_id"),
      prediction_action: "reuse",
      content_retention: "discard",
    };
    const output = document.querySelector("#evaluation-result");
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

const routes = {
  evaluate,
  articles,
  article: articleDetail,
  publishers,
  publisher: publisherDetail,
  models,
  jobs: jobsPage,
};

async function route() {
  routeController?.abort();
  const controller = new AbortController();
  routeController = controller;
  const current = parseLocation();
  document.querySelectorAll("nav [data-page]").forEach(link => {
    const activePage = current.page === "article" ? "articles" : current.page === "publisher" ? "publishers" : current.page;
    link.classList.toggle("active", link.dataset.page === activePage);
  });
  content.setAttribute("aria-busy", "true");
  try {
    await (routes[current.page] || evaluate)(current.id, current.params);
  } catch (error) {
    if (error.name === "AbortError" || routeController !== controller) return;
    content.innerHTML = pageHead("Request failed", "Unable to load this view", "") + errorCard(error.message);
  } finally {
    if (routeController === controller) content.setAttribute("aria-busy", "false");
  }
  if (routeController !== controller) return;
  window.scrollTo({top: 0, left: 0, behavior: "auto"});
  content.focus({preventScroll: true});
}

window.addEventListener("hashchange", route);
refreshSystemBadge();
route();
