/**
 * TEMPORARY — a panel for trying the candidate palettes in palettes.css.
 *
 * Delete this file, its import in app.js, and palettes.css once a palette is
 * chosen. It touches nothing else: it sets one attribute on <html>, which the
 * blocks in palettes.css key off, and remembers the choice in localStorage so it
 * survives a reload and every navigation.
 *
 * Open it with Shift+P, or step through the palettes with [ and ].
 */

const STORAGE_KEY = "prt-palette-preview";

const PALETTES = [
  ["", "Current (default)"],
  ["harbour", "Harbour — blue and amber"],
  ["terracotta", "Blue & Terracotta"],
  ["teal", "Blue & Teal"],
  ["mustard", "Navy & Mustard"],
  ["copper", "Slate & Copper"],
  ["forest", "Forest & Gold"],
  ["burgundy", "Oxford & Burgundy"],
  ["plum", "Olive & Plum"],
  ["retro", "Retro Grey"],
  ["newsprint", "Retro Newsprint"],
  ["blueprint", "Blueprint"],
  ["sage", "Sage & Clay"],
];

function stored() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "";
  } catch (error) {
    // Private windows and blocked site data both throw here; the preview simply
    // starts from the default palette in that case.
    return "";
  }
}

/** Apply a palette and remember it. An empty slug restores the stylesheet default. */
function apply(slug) {
  if (slug) document.documentElement.dataset.palette = slug;
  else delete document.documentElement.dataset.palette;
  try {
    localStorage.setItem(STORAGE_KEY, slug);
  } catch (error) {
    // Not being able to remember the choice is not a reason to refuse to show it.
  }
  document.querySelectorAll("#palette-panel button").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.slug === slug));
  });
}

function buildPanel() {
  const panel = document.createElement("div");
  panel.id = "palette-panel";
  panel.hidden = true;
  panel.innerHTML =
    `<p><b>Palette preview</b><br><small>Shift+P to hide · [ and ] to step</small></p>` +
    PALETTES.map(([slug, label]) =>
      `<button type="button" data-slug="${slug}">${label}</button>`).join("");
  panel.addEventListener("click", event => {
    const button = event.target.closest("button");
    if (button) apply(button.dataset.slug);
  });
  document.body.append(panel);
  return panel;
}

export function initPalettePreview() {
  const panel = buildPanel();
  apply(stored());

  document.addEventListener("keydown", event => {
    // Never steal a keystroke that is going into a field the user is filling in.
    const tag = event.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    if (event.shiftKey && event.key.toLowerCase() === "p") {
      panel.hidden = !panel.hidden;
      return;
    }
    if (event.key === "[" || event.key === "]") {
      const slugs = PALETTES.map(([slug]) => slug);
      const step = event.key === "]" ? 1 : -1;
      const next = (slugs.indexOf(stored()) + step + slugs.length) % slugs.length;
      apply(slugs[next]);
      panel.hidden = false;
    }
  });
}
