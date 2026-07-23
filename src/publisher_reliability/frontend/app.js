const content = document.querySelector("#content");
const stateBadge = document.querySelector("#system-state");
const warning = "Predictions are estimates, not fact checks. Softmax values are not necessarily calibrated confidence.";

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const shortId = (value) => `<span class="mono" title="${escapeHtml(value)}">${escapeHtml(String(value).slice(0, 12))}…</span>`;
const statusPill = (value) => `<span class="pill ${escapeHtml(value)}">${escapeHtml(value)}</span>`;
const pageHead = (eyebrow, title, intro, action = "") => `
  <header class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1>
  <p class="intro">${intro}</p></div>${action}</header>`;

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

async function dashboard() {
  const status = await api("/api/v1/status");
  stateBadge.textContent = status.offline ? "Ready · offline" : "Ready · local";
  const c = status.ledger_counts;
  content.innerHTML = pageHead("Local overview", "Research dashboard",
    "Inspect the prediction-only release, exact model identities, and persisted aggregation provenance.") + `
    <div class="grid">
      <section class="card"><div class="muted">Articles</div><div class="metric">${Number(c.prediction_runs).toLocaleString()}</div><p>Immutable prediction runs</p></section>
      <section class="card"><div class="muted">Models</div><div class="metric">${c.models}</div><p>Historical and runnable identities</p></section>
      <section class="card"><div class="muted">Evaluations</div><div class="metric">${c.evaluations}</div><p>Publisher results with exact membership</p></section>
      <section class="card wide"><h2>Scientific boundary</h2><div class="warning">${warning} This demo never calculates accuracy against protected labels.</div></section>
      <section class="card"><h2>Runtime</h2><p><b>Device:</b> ${escapeHtml(status.device)}<br><b>Schema:</b> ${escapeHtml(status.schema_version)}<br><b>Version:</b> ${escapeHtml(status.application_version)}</p></section>
    </div>`;
}

async function articles() {
  content.innerHTML = pageHead("Prediction history", "Articles",
    "Articles are derived from immutable prediction runs. Saved source text is never included here.",
    `<a class="button secondary" href="/api/v1/articles/export">Export CSV</a>`) + `<div class="loading">Loading articles…</div>`;
  const data = await api("/api/v1/articles?limit=25&sort=url_asc");
  content.querySelector(".loading").outerHTML = table(
    ["Article URL", "Publisher", "Models", "Runs", "Latest class"],
    data.items.map(row => `<tr><td><span class="url" title="${escapeHtml(row.canonical_url)}">${escapeHtml(row.canonical_url)}</span>${shortId(row.article_id)}</td>
      <td>${escapeHtml(row.normalized_hostname)}</td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td><span class="class-chip">${row.latest_predicted_class}</span></td></tr>`)
  );
}

async function publishers() {
  content.innerHTML = pageHead("Aggregation candidates", "Publishers",
    "Publisher identity is the normalized hostname; no homepage is invented.") + `<div class="loading">Loading publishers…</div>`;
  const data = await api("/api/v1/publishers?limit=25");
  content.querySelector(".loading").outerHTML = table(
    ["Publisher", "Articles", "Runs", "Evaluations", "Latest evaluation"],
    data.items.map(row => `<tr><td><b>${escapeHtml(row.normalized_hostname)}</b><br>${shortId(row.publisher_id)}</td>
      <td>${row.article_count}</td><td>${row.run_count}</td><td>${row.evaluation_count}</td>
      <td>${escapeHtml(row.latest_evaluation_at || "—")}</td></tr>`)
  );
}

async function models() {
  content.innerHTML = pageHead("Exact checkpoints", "Models",
    "Historical identities support browsing and aggregation. Add official artifacts before new inference.",
    `<button id="scan">Scan model roots</button>`) + `<div class="loading">Loading models…</div>`;
  document.querySelector("#scan").addEventListener("click", async (event) => {
    event.currentTarget.disabled = true;
    try {
      const result = await api("/api/v1/models/scan", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"});
      location.hash = "jobs";
    } catch (error) { event.currentTarget.disabled = false; alert(error.message); }
  });
  const data = await api("/api/v1/models");
  content.querySelector(".loading").outerHTML = table(
    ["Family / fold", "Model identity", "Support", "Status", "Runnable"],
    data.items.map(row => `<tr><td><b>${escapeHtml(row.family.toUpperCase())}</b> · fold ${row.fold_id}</td>
      <td>${shortId(row.model_id)}</td><td>${escapeHtml(row.support_level)}</td><td>${statusPill(row.status)}</td>
      <td>${row.runnable ? "Yes" : "No"}</td></tr>`)
  );
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
    "Long operations run through one FIFO worker. Refresh to inspect their latest macro phase.",
    `<button class="secondary" id="refresh">Refresh</button>`) + `<div class="loading">Loading jobs…</div>`;
  document.querySelector("#refresh").addEventListener("click", jobsPage);
  const data = await api("/api/v1/jobs?limit=25");
  content.querySelector(".loading").outerHTML = table(
    ["Created", "Type", "Status", "Phase", "Progress", "Result"],
    data.items.map(row => `<tr><td>${escapeHtml(row.created_at)}</td><td>${escapeHtml(row.job_type)}</td>
      <td>${statusPill(row.status)}</td><td>${escapeHtml(row.phase || "—")}</td><td>${row.progress}%</td>
      <td>${row.error_message ? `<span class="error">${escapeHtml(row.error_message)}</span>` : shortId(row.job_id)}</td></tr>`)
  );
}

async function evaluate() {
  const modelData = await api("/api/v1/models");
  const options = modelData.items.map(model => `<option value="${escapeHtml(model.model_id)}">${escapeHtml(model.family.toUpperCase())} fold ${model.fold_id} · ${escapeHtml(model.status)}</option>`).join("");
  content.innerHTML = pageHead("Stored prediction workflow", "Evaluate",
    "Reuse an exact historical prediction for one article, or aggregate stored predictions for one publisher.") + `
    <section class="card full"><form id="evaluation">
      <div class="row">
        <label>Input type<select name="type"><option value="article">Single article</option><option value="publisher">Publisher</option></select></label>
        <label>Model<select name="model_id">${options}</select></label>
        <label>Aggregation<select name="method"><option value="majority_vote">Majority vote</option><option value="ordinal_mean">Ordinal mean</option><option value="mean_probabilities">Mean probabilities</option></select></label>
      </div>
      <p><label>Article or publisher URL<input required name="url" type="url" size="70" placeholder="https://publisher.example/article"></label></p>
      <div class="row"><label>Publisher article count<input name="count" type="number" min="2" max="50" value="10"></label>
      <label><span>Partial result</span><select name="partial"><option value="true">Allow</option><option value="false">Require full count</option></select></label>
      <button>Start evaluation</button></div>
    </form><div id="evaluation-result" aria-live="polite"></div></section>
    <p class="warning">${warning}</p>`;
  document.querySelector("#evaluation").addEventListener("submit", async event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
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
      output.innerHTML = `<p class="notice">Evaluation accepted as job ${shortId(job.job_id)}. Follow its persisted status on the Jobs page.</p>`;
    } catch (error) { output.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`; }
  });
}

const routes = {dashboard, evaluate, articles, publishers, models, imports: importsPage, jobs: jobsPage};
async function route() {
  const page = location.hash.slice(1) || "dashboard";
  document.querySelectorAll("nav [data-page]").forEach(link => link.classList.toggle("active", link.dataset.page === page));
  content.innerHTML = `<div class="loading">Loading…</div>`;
  try { await (routes[page] || dashboard)(); }
  catch (error) { content.innerHTML = pageHead("Request failed", "Unable to load this view", "") + `<p class="error">${escapeHtml(error.message)}</p>`; }
  content.focus();
}
window.addEventListener("hashchange", route);
route();
