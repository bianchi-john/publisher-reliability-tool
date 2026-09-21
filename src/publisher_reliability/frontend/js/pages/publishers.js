/** #publishers — every publisher that has at least one stored prediction. */

import {api} from "../api.js";
import {pager, table} from "../components.js";
import {escapeHtml, shortId} from "../format.js";
import {mount, replaceLoading} from "../view.js";

const PAGE_SIZE = 25;

/* A character, not an icon file: the application loads no icon font and nothing
   from a CDN. It is drawn by whatever emoji font the reader's system has, so it
   is in colour and its exact shape varies between platforms. */
const MAGNIFIER = `<span class="emoji" aria-hidden="true">\u{1F50E}</span>`;

function publisherRow(row) {
  const href = `#publisher/${encodeURIComponent(row.publisher_id)}`;
  // The hostname is a link, which a table of numbers makes easy to overlook. The
  // button in the last column is what says the row opens a page of its own; its
  // label is for a screen reader, since on screen the glass is the whole message.
  const name = escapeHtml(row.normalized_hostname);
  return `<tr><td><a class="detail-link" href="${href}"><b>${name}</b></a><br>${shortId(row.publisher_id)}</td>
      <td>${row.article_count}</td><td>${row.model_count}</td><td>${row.run_count}</td>
      <td>${row.probability_run_count}</td>
      <td class="row-action"><a class="button inspect" href="${href}" title="Open ${name}" aria-label="Open ${name}">${MAGNIFIER}</a></td></tr>`;
}

export async function publishersPage(_id, params) {
  const offset = Number(params.get("offset") || 0);
  mount("publishers");
  const data = await api(`/api/v1/publishers?limit=${PAGE_SIZE}&offset=${offset}`);
  replaceLoading(table(
    ["Publisher", "Articles", "Models", "Predictions", "With probabilities",
     `<span class="row-action">Detail</span>`],
    data.items.map(publisherRow),
  ) + pager("publishers", data.page, data.items.length));
}
