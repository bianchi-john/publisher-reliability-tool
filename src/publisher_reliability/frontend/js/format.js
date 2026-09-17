/**
 * Text helpers shared by every page: escaping, and the human-readable names for
 * the enum-like values the API returns.
 */

/** Escape a value so it can be interpolated into HTML as text. */
export const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

/** Truncated identifier with the full value kept in the tooltip. */
export const shortId = (value) =>
  `<span class="mono" title="${escapeHtml(value)}">${escapeHtml(String(value).slice(0, 12))}…</span>`;

/** Coloured badge for a job or checkpoint status. */
export const statusPill = (value) =>
  `<span class="pill ${escapeHtml(value)}">${escapeHtml(value).replaceAll("_", " ")}</span>`;

/** Turn a snake_case job phase into a sentence-cased label. */
export const humanizePhase = (value) => {
  const text = String(value ?? "").replaceAll("_", " ").trim() || "working";
  return escapeHtml(text.charAt(0).toUpperCase() + text.slice(1));
};

/** Name of a model, falling back to "FAMILY · fold N" for dataset identities. */
export const modelLabel = (row) =>
  row.display_name || row.model_display_name || `${String(row.family).toUpperCase()} · fold ${row.fold_id}`;

/** Where a model came from. */
export const provenanceLabel = (value) => ({
  paper_official: "Paper original",
  user_custom: "User custom",
  paper_dataset: "Dataset identity",
  local_checkpoint: "Local checkpoint",
})[value] || value || "Unknown provenance";

/** How a stored prediction entered the workspace. */
export const originLabel = (origin) => ({
  bundled_import: "Original dataset",
  user_import: "Imported dataset",
  local_inference: "User evaluation",
})[origin] || origin;
