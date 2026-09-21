/**
 * #about — what this tool is, and the study it implements.
 *
 * The only page with no request behind it: its text is fixed, so it mounts the
 * template and is done. It still goes through the router like every other page,
 * so the navigation highlight and the scroll reset behave the same way here.
 */

import {mount} from "../view.js";

export function aboutPage() {
  mount("about");
}
