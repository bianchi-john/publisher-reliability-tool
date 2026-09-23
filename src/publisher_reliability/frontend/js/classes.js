/**
 * What a predicted class means, in words.
 *
 * The models output an integer from 0 to 4. Those integers are the NewsGuard
 * reliability bands the study trained on, in ascending order, and on their own
 * they tell a reader nothing: "Class 3" is not a statement anybody can act on.
 * Every place the interface shows a class therefore shows the band's name, and
 * keeps the number and the score range beside it so a result on screen can still
 * be matched to the CSV, to the API and to the paper, all of which speak in
 * numbers.
 *
 * The names are NewsGuard's own for its bands, and they describe the band, not
 * the publisher in front of you. What this tool shows is a model's prediction of
 * which band an article or a publisher falls in. It is not NewsGuard's rating of
 * that publisher, which this project holds but never redistributes.
 */

import {escapeHtml} from "./format.js";

/** Index is the class the models emit; the band is what that class means. */
export const CLASS_BANDS = [
  {name: "Proceed with Maximum Caution", range: "0–39"},
  {name: "Proceed with Caution", range: "40–59"},
  {name: "Credible with Exceptions", range: "60–74"},
  {name: "Generally Credible", range: "75–99"},
  {name: "High Credibility", range: "100"},
];

const band = (value) => CLASS_BANDS[Number(value)];

/** The band's name, or a plain "Class N" for a value outside the five. */
export function className(value) {
  return band(value)?.name ?? `Class ${value}`;
}

/** The provenance line: which class this is, and the scores the band covers. */
export function classDetail(value) {
  const entry = band(value);
  return entry ? `Class ${value} · NewsGuard band ${entry.range}` : `Class ${value}`;
}

/**
 * The band's score range on its own, for chart axes.
 *
 * Five names will not fit across a 520px plot, and abbreviating them would
 * invent vocabulary the rest of the interface does not use. The range is short,
 * ordered and unambiguous, and the full name is one hover away.
 */
export function classRange(value) {
  return band(value)?.range ?? String(value);
}

/** The chip the interface uses wherever one class has to be shown. */
export function classChip(value, {large = false} = {}) {
  if (value === null || value === undefined) return "";
  const size = large ? " large" : "";
  return `<span class="class-chip${size}" title="${escapeHtml(classDetail(value))}">`
    + `${escapeHtml(className(value))}</span>`;
}
