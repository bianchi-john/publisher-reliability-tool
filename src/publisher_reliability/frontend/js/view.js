/** Helpers for putting a rendered page into the main content area. */

import {render} from "./templates.js";

export const content = document.querySelector("#content");

/** Render a page template into the content area. Synchronous by design. */
export function mount(name, values = {}) {
  content.innerHTML = render(name, values);
}

/**
 * Swap the template's "Loading…" placeholder for the markup it was standing in for.
 *
 * Pages that fetch a single list mount their skeleton first and call this once the
 * rows arrive, so the header and tabs never flicker.
 */
export function replaceLoading(html) {
  content.querySelector(".loading").outerHTML = html;
}
