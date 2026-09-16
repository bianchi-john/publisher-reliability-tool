/**
 * Page markup lives in `frontend/pages/*.html`, so it can be edited as plain HTML.
 *
 * Every template is fetched once at start-up and cached. `render` is therefore
 * synchronous, which matters: a page must be able to put its skeleton on screen in
 * the same tick it is called, before it awaits any data.
 *
 * Placeholders are `{{name}}` and are replaced with the values a page passes in.
 * A value is inserted verbatim, so pages escape their own text (see `escapeHtml`)
 * and may equally pass a ready-made HTML fragment such as a table.
 */

const PAGE_TEMPLATES = [
  "evaluate", "articles", "article", "publishers", "publisher", "models", "jobs", "error",
  "prediction-result",
];

const cache = new Map();

/** Fetch every page template. Called once, before the first route is rendered. */
export async function loadTemplates() {
  await Promise.all(PAGE_TEMPLATES.map(async (name) => {
    const response = await fetch(`/assets/pages/${name}.html`);
    if (!response.ok) throw new Error(`Cannot load the ${name} page template.`);
    cache.set(name, await response.text());
  }));
}

/** Fill a cached template with `values`; unknown placeholders become empty. */
export function render(name, values = {}) {
  const template = cache.get(name);
  if (template === undefined) throw new Error(`Unknown page template: ${name}`);
  return template.replace(/\{\{(\w+)\}\}/g, (_match, key) => values[key] ?? "");
}
