/** #articles — the list of articles, filterable by where they came from. */

import {api} from "../api.js";
import {articleSourceBadges, pager, table} from "../components.js";
import {escapeHtml, shortId} from "../format.js";
import {mount, replaceLoading} from "../view.js";

const PAGE_SIZE = 25;

function articleRow(row) {
  const rowClass = row.source_type === "user_evaluation" ? "user-article-row" : "dataset-article-row";
  return `<tr class="${rowClass}"><td><a class="url detail-link" href="#article/${encodeURIComponent(row.article_id)}" title="${escapeHtml(row.canonical_url)}">${escapeHtml(row.canonical_url)}</a>${shortId(row.article_id)}</td>
      <td>${articleSourceBadges(row)}</td>
      <td><a class="detail-link" href="#publisher/${encodeURIComponent(row.publisher_id)}">${escapeHtml(row.normalized_hostname)}</a></td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td><span class="class-chip">Class ${row.latest_predicted_class}</span></td></tr>`;
}

export async function articlesPage(_id, params) {
  const offset = Number(params.get("offset") || 0);
  const source = params.get("source") || "";
  const sourceQuery = source ? `&article_source=${encodeURIComponent(source)}` : "";
  const pageBase = source ? `articles?source=${encodeURIComponent(source)}` : "articles";

  mount("articles", {
    exportQuery: source ? `?article_source=${encodeURIComponent(source)}` : "",
    allTab: source ? "" : "active",
    datasetTab: source === "dataset" ? "active" : "",
    userTab: source === "user_evaluation" ? "active" : "",
  });

  const data = await api(`/api/v1/articles?limit=${PAGE_SIZE}&sort=url_asc&offset=${offset}${sourceQuery}`);
  replaceLoading(table(
    ["Article URL", "Source", "Publisher", "Models", "Predictions", "Latest label"],
    data.items.map(articleRow),
  ) + pager(pageBase, data.page));
}
