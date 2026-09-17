/** #publishers — every publisher that has at least one stored prediction. */

import {api} from "../api.js";
import {pager, table} from "../components.js";
import {escapeHtml, shortId} from "../format.js";
import {mount, replaceLoading} from "../view.js";

const PAGE_SIZE = 25;

function publisherRow(row) {
  return `<tr><td><a class="detail-link" href="#publisher/${encodeURIComponent(row.publisher_id)}"><b>${escapeHtml(row.normalized_hostname)}</b></a><br>${shortId(row.publisher_id)}</td>
      <td>${row.article_count}</td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td>${row.probability_run_count}</td></tr>`;
}

export async function publishersPage(_id, params) {
  const offset = Number(params.get("offset") || 0);
  mount("publishers");
  const data = await api(`/api/v1/publishers?limit=${PAGE_SIZE}&offset=${offset}`);
  replaceLoading(table(
    ["Publisher", "Articles", "Models", "Predictions", "With probabilities"],
    data.items.map(publisherRow),
  ) + pager("publishers", data.page, data.items.length));
}
