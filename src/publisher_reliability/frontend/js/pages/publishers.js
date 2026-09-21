/** #publishers — every publisher that has at least one stored prediction. */

import {api} from "../api.js";
import {pager, table} from "../components.js";
import {escapeHtml, shortId} from "../format.js";
import {mount, replaceLoading} from "../view.js";

const PAGE_SIZE = 25;

function publisherRow(row) {
  // The hostname stays a link, because that is where the eye goes first and people
  // do click it. The button at the end of the row is what says where the click
  // leads: a table of counts gives no hint that a row is an entrance to a page.
  const href = `#publisher/${encodeURIComponent(row.publisher_id)}`;
  return `<tr><td><a class="detail-link" href="${href}"><b>${escapeHtml(row.normalized_hostname)}</b></a><br>${shortId(row.publisher_id)}</td>
      <td>${row.article_count}</td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td>${row.probability_run_count}</td>
      <td class="row-action"><a class="button secondary compact" href="${href}">Reliability class <span aria-hidden="true">&rarr;</span></a></td></tr>`;
}

export async function publishersPage(_id, params) {
  const offset = Number(params.get("offset") || 0);
  mount("publishers");
  const data = await api(`/api/v1/publishers?limit=${PAGE_SIZE}&offset=${offset}`);
  replaceLoading(table(
    ["Publisher", "Articles", "Models", "Predictions", "With probabilities",
     // The column is self-explanatory on screen but still needs a name for a
     // screen reader, which reads the header before each cell of the column.
     `<span class="sr-only">Open the publisher page</span>`],
    data.items.map(publisherRow),
    "linked-rows",
  ) + pager("publishers", data.page, data.items.length));
}
