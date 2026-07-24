const content = document.querySelector("#content");
const stateBadge = document.querySelector("#system-state");
const warning = "Predictions are estimates, not fact checks. Softmax values are not necessarily calibrated confidence.";

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const shortId = (value) => `<span class="mono" title="${escapeHtml(value)}">${escapeHtml(String(value).slice(0, 12))}…</span>`;
const statusPill = (value) => `<span class="pill ${escapeHtml(value)}">${escapeHtml(value).replaceAll("_", " ")}</span>`;
const pageHead = (eyebrow, title, intro, action = "") => `
  <header class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1>
  <p class="intro">${intro}</p></div>${action}</header>`;
const modelLabel = (row) => `${String(row.family).toUpperCase()} · fold ${row.fold_id}`;

async function api(path, options = {}) {
  const response = await fetch(path, options);
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
  const raw = location.hash.slice(1) || "dashboard";
  const [path, query = ""] = raw.split("?", 2);
  const parts = path.split("/").filter(Boolean);
  return {page: parts[0] || "dashboard", id: parts[1] || "", params: new URLSearchParams(query)};
}

function probabilityCells(run) {
  if (!run.probabilities) {
    return `<td colspan="5"><span class="muted">Not supplied by this model in the dataset</span></td>`;
  }
  return run.probabilities.map(value => `<td class="mono probability">${(Number(value) * 100).toFixed(2)}%</td>`).join("");
}

function pager(base, page) {
  const previous = page.offset > 0
    ? `<a class="button secondary" href="#${base}?offset=${Math.max(0, page.offset - page.limit)}">Previous</a>`
    : "";
  const next = page.next_offset !== null
    ? `<a class="button secondary" href="#${base}?offset=${page.next_offset}">Next</a>`
    : "";
  return previous || next ? `<div class="pager">${previous}<span class="muted">Rows ${page.offset + 1}–${page.offset + page.limit}</span>${next}</div>` : "";
}

async function dashboard() {
  const status = await api("/api/v1/status");
  stateBadge.textContent = status.offline ? "Ready · offline" : "Ready · local";
  const c = status.ledger_counts;
  const d = status.derived_counts;
  content.innerHTML = pageHead("Local overview", "Research dashboard",
    "Browse every imported prediction separately from publisher aggregations created in this workspace.") + `
    <div class="grid">
      <section class="card"><div class="muted">Articles</div><div class="metric">${Number(d.articles).toLocaleString()}</div><p>Distinct articles represented in prediction history</p></section>
      <section class="card"><div class="muted">Stored predictions</div><div class="metric">${Number(d.historical_predictions).toLocaleString()}</div><p>Immutable model outputs imported from datasets</p></section>
      <section class="card"><div class="muted">Complete probability vectors</div><div class="metric">${Number(d.predictions_with_probabilities).toLocaleString()}</div><p>Every bundled BERT/RoBERTa run contains all five classes</p></section>
      <section class="card"><div class="muted">Publishers</div><div class="metric">${Number(d.publishers).toLocaleString()}</div><p>Normalized publisher identities</p></section>
      <section class="card"><div class="muted">Created aggregations</div><div class="metric">${Number(c.evaluations).toLocaleString()}</div><p>Publisher-level results explicitly created here</p></section>
      <section class="card"><div class="muted">Model identities</div><div class="metric">${Number(c.models).toLocaleString()}</div><p>Historical identities plus validated local checkpoints</p></section>
      <section class="card wide"><h2>How counts differ</h2><div class="notice"><b>Stored predictions</b> are the article-level evaluations already present in the imported dataset. <b>Created aggregations</b> combine several of those predictions for one publisher and start at zero until you create one.</div></section>
      <section class="card"><h2>Runtime</h2><p><b>Device:</b> ${escapeHtml(status.device)}<br><b>Schema:</b> ${escapeHtml(status.schema_version)}<br><b>Version:</b> ${escapeHtml(status.application_version)}</p></section>
      <section class="card full"><div class="warning">${warning} This tool never calculates accuracy against protected labels.</div></section>
    </div>`;
}

async function articles(_id, params) {
  const offset = Number(params.get("offset") || 0);
  content.innerHTML = pageHead("Prediction history", "Articles & predictions",
    "Open an article to inspect every stored model output and every available class probability.",
    `<a class="button secondary" href="/api/v1/articles/export">Export CSV</a>`) + `<div class="loading">Loading articles…</div>`;
  const data = await api(`/api/v1/articles?limit=25&sort=url_asc&offset=${offset}`);
  content.querySelector(".loading").outerHTML = table(
    ["Article URL", "Publisher", "Models", "Predictions", "Latest class"],
    data.items.map(row => `<tr><td><a class="url detail-link" href="#article/${encodeURIComponent(row.article_id)}" title="${escapeHtml(row.canonical_url)}">${escapeHtml(row.canonical_url)}</a>${shortId(row.article_id)}</td>
      <td>${escapeHtml(row.normalized_hostname)}</td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td><span class="class-chip">${row.latest_predicted_class}</span></td></tr>`)
  ) + pager("articles", data.page);
}

async function articleDetail(id) {
  const row = await api(`/api/v1/articles/${encodeURIComponent(id)}`);
  content.innerHTML = pageHead("Article prediction history", row.normalized_hostname,
    row.canonical_url, `<a class="button secondary" href="#articles">Back to articles</a>`) + `
    <div class="grid detail-metrics">
      <section class="card"><div class="muted">Models</div><div class="metric">${row.model_count}</div></section>
      <section class="card"><div class="muted">Stored predictions</div><div class="metric">${row.run_count}</div></section>
      <section class="card"><div class="muted">Latest class</div><div class="metric">${row.latest_predicted_class}</div></section>
    </div>
    <section class="section-block"><h2>Every model prediction</h2>
    ${table(
      ["Model / fold", "Predicted class", "P(class 0)", "P(class 1)", "P(class 2)", "P(class 3)", "P(class 4)", "Origin", "Run"],
      row.runs.map(run => `<tr><td><b>${escapeHtml(String(run.family || "unknown").toUpperCase())}</b><br>fold ${run.fold_id ?? "—"}</td>
        <td><span class="class-chip">${run.predicted_class}</span></td>${probabilityCells(run)}
        <td>${escapeHtml(run.origin)}</td><td>${shortId(run.prediction_run_id)}</td></tr>`)
    )}</section><p class="warning">${warning}</p>`;
}

async function publishers(_id, params) {
  const offset = Number(params.get("offset") || 0);
  content.innerHTML = pageHead("Dataset coverage", "Publishers",
    "Predictions are imported article-level outputs; aggregations are publisher results explicitly created in this workspace.") + `<div class="loading">Loading publishers…</div>`;
  const data = await api(`/api/v1/publishers?limit=25&offset=${offset}`);
  content.querySelector(".loading").outerHTML = table(
    ["Publisher", "Articles", "Models", "Predictions", "With probabilities", "Created aggregations"],
    data.items.map(row => `<tr><td><a class="detail-link" href="#publisher/${encodeURIComponent(row.publisher_id)}"><b>${escapeHtml(row.normalized_hostname)}</b></a><br>${shortId(row.publisher_id)}</td>
      <td>${row.article_count}</td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td>${row.probability_run_count}</td><td>${row.evaluation_count}</td></tr>`)
  ) + pager("publishers", data.page);
}

async function publisherDetail(id, params) {
  const offset = Number(params.get("offset") || 0);
  const [publisher, runs] = await Promise.all([
    api(`/api/v1/publishers/${encodeURIComponent(id)}`),
    api(`/api/v1/prediction-runs?publisher_id=${encodeURIComponent(id)}&limit=100&offset=${offset}`),
  ]);
  content.innerHTML = pageHead("Publisher dataset history", publisher.normalized_hostname,
    "Every stored BERT/RoBERTa prediction is listed below with its complete five-class probability vector.",
    `<a class="button secondary" href="#publishers">Back to publishers</a>`) + `
    <div class="grid detail-metrics">
      <section class="card"><div class="muted">Articles</div><div class="metric">${publisher.article_count}</div></section>
      <section class="card"><div class="muted">Stored predictions</div><div class="metric">${publisher.run_count}</div></section>
      <section class="card"><div class="muted">Created aggregations</div><div class="metric">${publisher.evaluation_count}</div></section>
    </div>
    <section class="section-block"><h2>Stored predictions</h2>
    ${table(
      ["Article", "Model / fold", "Class", "P(0)", "P(1)", "P(2)", "P(3)", "P(4)", "Run"],
      runs.items.map(run => `<tr><td><a class="url detail-link" href="#article/${encodeURIComponent(run.article_id)}" title="${escapeHtml(run.canonical_url)}">${escapeHtml(run.canonical_url)}</a></td>
        <td><b>${escapeHtml(String(run.family || "unknown").toUpperCase())}</b><br>fold ${run.fold_id ?? "—"}</td>
        <td><span class="class-chip">${run.predicted_class}</span></td>${probabilityCells(run)}
        <td>${shortId(run.prediction_run_id)}</td></tr>`)
    )}${pager(`publisher/${encodeURIComponent(id)}`, runs.page)}</section>
    <section class="section-block"><h2>Created publisher aggregations</h2>
      ${publisher.evaluations.length ? table(
        ["Created", "Model", "Method", "Articles used", "Result"],
        publisher.evaluations.map(item => `<tr><td>${escapeHtml(item.created_at)}</td><td>${shortId(item.model_id)}</td>
          <td>${escapeHtml(item.method)}</td><td>${item.used_count}</td><td><span class="class-chip">${item.result_class}</span></td></tr>`)
      ) : `<div class="empty notice">No publisher aggregation has been created yet. The stored predictions above are still fully available for consultation.</div>`}
    </section><p class="warning">${warning}</p>`;
}

async function waitForJob(jobId, output) {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const job = await api(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
    output.textContent = `${job.phase || job.status} · ${job.progress}%`;
    if (job.status === "succeeded") return job;
    if (job.status === "failed") throw new Error(job.error_message || "Model scan failed.");
    await new Promise(resolve => setTimeout(resolve, 750));
  }
  throw new Error("Model scan is still running; inspect it on the Jobs page.");
}

function renderModelTables(items) {
  const local = items.filter(row => row.identity_kind === "local");
  const historical = items.filter(row => row.identity_kind === "historical");
  return `
    <section class="section-block"><h2>Local and imported models</h2>
      <p class="muted">Models marked Ready can classify new article URLs. Core .pt checkpoints are discovered in configured directories; custom Transformers are installed from the ZIP form above.</p>
      ${table(
        ["Checkpoint", "Digest", "Status", "Available", "Inference"],
        local.map(row => `<tr><td><b>${escapeHtml(modelLabel(row))}</b><br><span class="mono">${escapeHtml(row.artifact_locator)}</span></td>
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
    "Core BERT/RoBERTa checkpoints are scanned automatically. User-created Transformers are imported as a self-contained safe bundle.",
    `<button id="scan">Rescan model directories</button>`) + `
    <section class="card full"><h2>Import custom Transformer</h2>
      <ol>
        <li>Export the model with <span class="mono">model.save_pretrained(..., safe_serialization=True)</span> and export its tokenizer with <span class="mono">tokenizer.save_pretrained(...)</span>.</li>
        <li>Add <span class="mono">prt-model.json</span> to that same folder, then compress the complete folder as one <span class="mono">.zip</span>.</li>
        <li>Select that ZIP below. A standalone <span class="mono">.pt</span> file is not a custom bundle.</li>
      </ol>
      <details><summary>Required files and manifest example</summary>
        <p class="muted">Required: prt-model.json, config.json, model.safetensors, tokenizer_config.json, plus all tokenizer resources.</p>
        <pre class="mono">${escapeHtml(`{
  "schema_version": 1,
  "display_name": "My custom classifier",
  "family": "custom_my_model",
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
      scanState.innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
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
      scanState.innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
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

async function importsPage() {
  content.innerHTML = pageHead("Dataset provenance", "Imports",
    "Upload CSV or CSV.GZ predictions. Editorial and protected values are discarded before persistence.") + `
    <section class="card full"><form id="upload"><div class="row"><label>Prediction dataset
      <input required name="file" type="file" accept=".csv,.gz"></label><button>Import dataset</button></div></form>
      <div id="upload-result" aria-live="polite"></div></section><div class="loading">Loading imports…</div>`;
  document.querySelector("#upload").addEventListener("submit", async event => {
    event.preventDefault();
    const result = document.querySelector("#upload-result");
    result.textContent = "Acquiring upload…";
    try {
      const body = new FormData(event.currentTarget);
      const job = await api("/api/v1/imports/upload", {method: "POST", body});
      result.innerHTML = `<p>Import accepted as job ${shortId(job.job_id)}</p>`;
    } catch (error) { result.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`; }
  });
  const data = await api("/api/v1/imports?limit=25");
  content.querySelector(".loading").outerHTML = table(
    ["Source", "Status", "Rows", "Accepted", "Digest"],
    data.items.map(row => `<tr><td>${escapeHtml(row.source_name)}<br><span class="muted">${escapeHtml(row.source_kind)}</span></td>
      <td>${statusPill(row.status)}</td><td>${row.source_rows}</td><td>${row.accepted_rows}</td><td>${shortId(row.content_sha256)}</td></tr>`)
  );
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
  content.innerHTML = pageHead("Stored prediction workflow", "Evaluate",
    "Enter an article or publisher first. The model list is built only from compatible predictions that actually exist for that input.") + `
    <section class="card full"><form id="evaluation">
      <div class="row">
        <label>Input type<select name="type"><option value="article">Single article</option><option value="publisher">Publisher</option></select></label>
        <label class="grow">Article or publisher URL<input required name="url" type="url" placeholder="https://publisher.example/article"></label>
      </div>
      <div class="row evaluation-options">
        <label>Available stored model<select required disabled name="model_id"><option value="">Enter a valid URL first</option></select></label>
        <label class="publisher-only">Aggregation method<select name="method"><option value="majority_vote">Majority vote</option><option value="ordinal_mean">Ordinal mean</option><option value="mean_probabilities">Mean probabilities</option></select>
          <small>How the selected article predictions are combined into one publisher result.</small></label>
        <label class="publisher-only">Requested safe articles<input name="count" type="number" min="2" max="50" value="10">
          <small>Maximum number of held-out article predictions to aggregate.</small></label>
        <label class="publisher-only"><span>When fewer articles are available</span><select name="partial"><option value="true">Use the available articles</option><option value="false">Require the full count</option></select>
          <small>“Use available” creates a partial result with at least two safe articles; “require” fails unless the requested count is reached.</small></label>
      </div>
      <div id="model-availability" class="notice" aria-live="polite">Models will be detected from stored predictions for this input.</div>
      <div class="row"><button disabled>Start evaluation</button></div>
    </form><div id="evaluation-result" aria-live="polite"></div></section>
    <section class="section-block"><h2>Previously created publisher aggregations</h2><div id="saved-evaluations" class="loading">Loading aggregations…</div></section>
    <p class="warning">${warning}</p>`;

  const form = document.querySelector("#evaluation");
  const typeField = form.elements.type;
  const urlField = form.elements.url;
  const modelField = form.elements.model_id;
  const countField = form.elements.count;
  const partialField = form.elements.partial;
  const availability = document.querySelector("#model-availability");
  const submit = form.querySelector("button[type='submit'], button:not([type])");
  let timer;

  function updateFieldState() {
    const publisher = typeField.value === "publisher";
    form.querySelectorAll(".publisher-only").forEach(element => { element.hidden = !publisher; });
    form.elements.method.disabled = !publisher;
    countField.disabled = !publisher;
    partialField.disabled = !publisher;
  }

  async function refreshAvailable() {
    clearTimeout(timer);
    if (!urlField.validity.valid || !urlField.value) {
      modelField.innerHTML = `<option value="">Enter a valid URL first</option>`;
      modelField.disabled = true;
      submit.disabled = true;
      return;
    }
    availability.textContent = "Detecting compatible stored predictions…";
    const query = new URLSearchParams({
      input_type: typeField.value,
      url: urlField.value,
      requested_count: countField.value || "2",
      allow_partial: partialField.value,
    });
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
      availability.innerHTML = `<b>${escapeHtml(data.availability.message)}</b>${
        blocked.length
          ? `<br><span class="muted">Blocked to prevent training leakage: ${blocked.map(row => escapeHtml(modelLabel(row))).join(", ")}.</span>`
          : ""
      }`;
    } catch (error) {
      modelField.disabled = true;
      submit.disabled = true;
      availability.innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
    }
  }

  function scheduleRefresh() {
    clearTimeout(timer);
    timer = setTimeout(refreshAvailable, 350);
  }
  typeField.addEventListener("change", () => { updateFieldState(); refreshAvailable(); });
  urlField.addEventListener("input", scheduleRefresh);
  countField.addEventListener("change", refreshAvailable);
  partialField.addEventListener("change", refreshAvailable);
  updateFieldState();

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const data = new FormData(form);
    const type = data.get("type");
    const input = type === "article"
      ? {type, url: data.get("url")}
      : {type, url: data.get("url"), requested_article_count: Number(data.get("count")), allow_partial: data.get("partial") === "true"};
    const body = {input, model_id: data.get("model_id"), prediction_action: "reuse", content_retention: "discard"};
    if (type !== "article") body.aggregation_method = data.get("method");
    const output = document.querySelector("#evaluation-result");
    output.textContent = "Submitting evaluation…";
    try {
      const job = await api("/api/v1/evaluation-jobs", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      output.innerHTML = `<p class="notice">Evaluation accepted as job ${shortId(job.job_id)}. Retrieving and classifying may take a little while on CPU.</p>`;
      const completed = await waitForJob(job.job_id, output);
      if (type === "article") {
        output.innerHTML = `<section class="card"><h2>Article prediction</h2>
          <p><span class="class-chip">Class ${completed.result.predicted_class}</span>
          ${completed.result.reused ? "Reused stored prediction" : "New local inference"}</p>
          <div class="probabilities">${completed.result.probabilities.map((value, index) =>
            `<span><b>C${index}</b> ${Number(value).toFixed(6)}</span>`).join("")}</div>
          <p class="muted">Run ${shortId(completed.result.prediction_run_id)}</p></section>`;
      } else {
        output.innerHTML = `<p class="notice">Evaluation completed: Class ${completed.result.result_class}, using ${completed.result.used_count} article(s).</p>`;
      }
    } catch (error) { output.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`; }
  });

  const evaluations = await api("/api/v1/evaluations?limit=25");
  document.querySelector("#saved-evaluations").outerHTML = evaluations.items.length
    ? table(
      ["Publisher", "Model", "Method", "Articles", "Result", "Created"],
      evaluations.items.map(row => `<tr><td>${escapeHtml(row.normalized_hostname)}</td><td>${shortId(row.model_id)}</td>
        <td>${escapeHtml(row.method)}</td><td>${row.used_count}</td><td><span class="class-chip">${row.result_class}</span></td><td>${escapeHtml(row.created_at)}</td></tr>`)
    )
    : `<div class="empty notice">No publisher aggregation has been created yet. This does not mean the imported article predictions are missing; browse them under Articles or Publishers.</div>`;
}

const routes = {
  dashboard,
  evaluate,
  articles,
  article: articleDetail,
  publishers,
  publisher: publisherDetail,
  models,
  imports: importsPage,
  jobs: jobsPage,
};

async function route() {
  const current = parseLocation();
  document.querySelectorAll("nav [data-page]").forEach(link => {
    const activePage = current.page === "article" ? "articles" : current.page === "publisher" ? "publishers" : current.page;
    link.classList.toggle("active", link.dataset.page === activePage);
  });
  content.innerHTML = `<div class="loading">Loading…</div>`;
  try { await (routes[current.page] || dashboard)(current.id, current.params); }
  catch (error) { content.innerHTML = pageHead("Request failed", "Unable to load this view", "") + `<p class="error">${escapeHtml(error.message)}</p>`; }
  content.focus();
}

window.addEventListener("hashchange", route);
route();
