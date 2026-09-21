/**
 * Entry point.
 *
 * Page markup lives in `frontend/pages/*.html`; each page under `js/pages/` fills
 * one of those templates and wires up its own controls. This file only loads the
 * templates, says which page answers which route, and starts the interface.
 */

import {api} from "./api.js";
import {errorCard} from "./components.js";
import {registerPage, startRouter} from "./router.js";
import {loadTemplates} from "./templates.js";
import {initPalettePreview} from "./palette-preview.js";  // TEMPORARY
import {initTopbar} from "./topbar.js";
import {content} from "./view.js";

import {aboutPage} from "./pages/about.js";
import {articleDetailPage} from "./pages/article.js";
import {articlesPage} from "./pages/articles.js";
import {evaluatePage} from "./pages/evaluate.js";
import {jobsPage} from "./pages/jobs.js";
import {modelsPage} from "./pages/models.js";
import {publisherDetailPage} from "./pages/publisher.js";
import {publishersPage} from "./pages/publishers.js";

registerPage("evaluate", evaluatePage);
registerPage("articles", articlesPage);
registerPage("article", articleDetailPage);
registerPage("publishers", publishersPage);
registerPage("publisher", publisherDetailPage);
registerPage("models", modelsPage);
registerPage("jobs", jobsPage);
registerPage("about", aboutPage);

/** Record what this deployment serves, so local-only controls can be hidden. */
async function markInstanceKind() {
  try {
    const status = await api("/api/v1/status");
    document.body.dataset.publicInstance = String(Boolean(status.public_instance));
  } catch (error) {
    // A failed status read must not block the interface; the controls simply stay
    // visible and their own requests report any problem.
  }
}

async function start() {
  initTopbar();
  initPalettePreview();  // TEMPORARY: remove with the palette files.
  await markInstanceKind();
  try {
    // Templates are cached up front so pages can render without awaiting them.
    await loadTemplates();
  } catch (error) {
    content.innerHTML = errorCard(error.message);
    return;
  }
  startRouter();
}

start();
