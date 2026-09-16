/**
 * Hash routing: `#page/id?query` picks one page module and hands it the id and
 * query parameters.
 *
 * Every navigation opens a new request scope, so anything the previous page was
 * still fetching is aborted and cannot render over the new one.
 */

import {isActiveScope, openRequestScope} from "./api.js";
import {errorCard} from "./components.js";
import {content, mount} from "./view.js";

const DEFAULT_PAGE = "evaluate";

/** Detail pages keep their parent's nav entry highlighted. */
const NAV_PARENT = {article: "articles", publisher: "publishers"};

const pages = new Map();

/** Register the handler for one `#page` route. */
export function registerPage(name, handler) {
  pages.set(name, handler);
}

/** Split the current hash into page name, optional id and query parameters. */
export function parseLocation() {
  const raw = location.hash.slice(1) || DEFAULT_PAGE;
  const [path, query = ""] = raw.split("?", 2);
  const parts = path.split("/").filter(Boolean);
  return {page: parts[0] || DEFAULT_PAGE, id: parts[1] || "", params: new URLSearchParams(query)};
}

function highlightNav(page) {
  const activePage = NAV_PARENT[page] || page;
  document.querySelectorAll("nav [data-page]").forEach(link => {
    link.classList.toggle("active", link.dataset.page === activePage);
  });
}

/** Render the page the current hash points at. */
export async function route() {
  const controller = openRequestScope();
  const current = parseLocation();
  highlightNav(current.page);
  content.setAttribute("aria-busy", "true");
  try {
    await (pages.get(current.page) || pages.get(DEFAULT_PAGE))(current.id, current.params);
  } catch (error) {
    // A superseded navigation is not a failure worth reporting.
    if (error.name === "AbortError" || !isActiveScope(controller)) return;
    mount("error", {errorCard: errorCard(error.message)});
  } finally {
    if (isActiveScope(controller)) content.setAttribute("aria-busy", "false");
  }
  if (!isActiveScope(controller)) return;
  window.scrollTo({top: 0, left: 0, behavior: "auto"});
  content.focus({preventScroll: true});
}

/** Render the current hash and keep following hash changes. */
export function startRouter() {
  window.addEventListener("hashchange", route);
  route();
}
