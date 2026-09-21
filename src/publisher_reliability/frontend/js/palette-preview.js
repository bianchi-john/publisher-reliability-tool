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
  ["blacktext", "Current, but black text"],
  // Today's blue and light frame on white paper, differing in the buttons.
  ["c-square", "Classic · square buttons"],
  ["c-pill", "Classic · pill buttons"],
  ["c-outline", "Classic · outline buttons"],
  ["c-raised", "Classic · raised buttons"],
  ["c-key", "Classic · keycap buttons"],
  ["c-soft", "Classic · soft buttons"],
  ["c-slab", "Classic · ink slab buttons"],
  ["c-amber", "Classic · amber action"],
  ["c-duo", "Classic · blue and amber pair"],
  // A coloured frame around white content.
  ["ink", "Bold · Ink & Amber"],
  ["oxford", "Bold · Oxford & Rust"],
  ["bottle", "Bold · Bottle & Gold"],
  ["cobalt", "Bold · Cobalt & Coral"],
  ["teal", "Bold · Teal & Magenta"],
  ["plum", "Bold · Plum & Lime"],
  ["burgundy", "Bold · Burgundy & Brass"],
  ["petrol", "Bold · Petrol & Apricot"],
  ["retro", "Bold · Retro Grey & Red"],
  ["newsprint", "Bold · Retro Newsprint"],
  ["blueprint", "Bold · Blueprint"],
  ["forest", "Bold · Forest & Clay"],
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
