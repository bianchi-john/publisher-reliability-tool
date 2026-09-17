/**
 * Hand-rolled inline SVG charts for the publisher aggregation view.
 *
 * There is no charting library here on purpose: the application ships no build step
 * and loads nothing from a CDN, so every chart is a plain string of SVG built from
 * the numbers the API returned. That also keeps them readable — each function below
 * is a small, self-contained drawing you can follow line by line and change by hand.
 *
 * Shared conventions:
 *   - every chart draws into a fixed viewBox and scales with its container, so the
 *     caller only decides the width;
 *   - colours come from the stylesheet's custom properties, never hard-coded, so the
 *     palette stays in one place;
 *   - a chart with nothing to show returns an explanatory note instead of empty axes.
 */

import {escapeHtml} from "./format.js";

/** The five reliability classes, from least to most reliable. */
const CLASSES = [0, 1, 2, 3, 4];

/** Where each chart's plot area sits inside its viewBox. */
const PAD = {top: 16, right: 16, bottom: 34, left: 40};

const note = (text) => `<p class="chart-empty muted">${escapeHtml(text)}</p>`;

/** Round to a sane number of decimals without printing floating-point noise. */
const number = (value, decimals = 2) =>
  value === null || value === undefined ? "—" : Number(value).toFixed(decimals);

const percent = (value) =>
  value === null || value === undefined ? "—" : `${(Number(value) * 100).toFixed(0)}%`;

/**
 * Wrap drawn elements in a titled, accessible SVG figure.
 *
 * `caption` is the sentence that explains what the reader is looking at. A legend is
 * HTML rather than SVG text so it wraps on a narrow screen: text inside an SVG is
 * laid out at authoring coordinates and would simply overlap instead.
 */
function figure(title, caption, width, height, body, legend = "") {
  return `<figure class="chart">
    <figcaption><b>${escapeHtml(title)}</b><span class="muted">${escapeHtml(caption)}</span></figcaption>
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}" preserveAspectRatio="xMidYMid meet">${body}</svg>
    ${legend ? `<div class="chart-legend">${legend}</div>` : ""}
  </figure>`;
}

/** One legend entry: a swatch drawn with the same class as the bars it names. */
const legendItem = (className, label) =>
  `<span class="legend-item"><span class="legend-swatch ${escapeHtml(className)}"></span>${escapeHtml(label)}</span>`;

/**
 * Horizontal gridlines with their value labels, drawn behind the data.
 * `format` decides how the labels read: counts as integers, shares as percentages.
 */
function gridlines(width, height, maximum, {steps = 4, format = "auto"} = {}) {
  const label = (value) => format === "percent" ? percent(value) : number(value, maximum <= 1 ? 2 : 0);
  const parts = [];
  for (let step = 0; step <= steps; step += 1) {
    const value = (maximum * step) / steps;
    const y = height - PAD.bottom - ((height - PAD.top - PAD.bottom) * step) / steps;
    parts.push(`<line class="grid" x1="${PAD.left}" y1="${y}" x2="${width - PAD.right}" y2="${y}"></line>`);
    parts.push(`<text class="axis" x="${PAD.left - 6}" y="${y + 4}" text-anchor="end">${label(value)}</text>`);
  }
  return parts.join("");
}

/** The class labels along the bottom of a five-column chart. */
function classAxis(width, height, columnWidth) {
  return CLASSES.map(index => {
    const x = PAD.left + columnWidth * (index + 0.5);
    return `<text class="axis" x="${x}" y="${height - PAD.bottom + 18}" text-anchor="middle">Class ${index}</text>`;
  }).join("");
}

/**
 * How many articles landed in each class, optionally beside the weighted counts the
 * chosen method actually used. Seeing the raw and the weighted bars together is the
 * only way to tell whether confidence weighting moved the verdict.
 */
export function classDistribution(group) {
  const counts = CLASSES.map(index => Number(group.class_counts[String(index)] || 0));
  if (!counts.some(value => value > 0)) return note("No counted article to plot.");

  // Only overlay the weights the method used when they are on the same scale as the
  // counts and actually differ from them. In practice that is the confidence-weighted
  // vote alone: a plain majority weights nothing, and the probability methods report
  // their averaged vector, which the profile chart draws properly.
  const raw = Array.isArray(group.weighted_counts) ? group.weighted_counts.map(Number) : null;
  const weighted = raw
    && Math.max(...raw) > 1.0001
    && raw.some((value, index) => Math.abs(value - counts[index]) > 1e-6)
    ? raw
    : null;
  const maximum = Math.max(...counts, weighted ? Math.max(...weighted) : 0) * 1.1 || 1;

  const width = 520;
  const height = 240;
  const plot = height - PAD.top - PAD.bottom;
  const columnWidth = (width - PAD.left - PAD.right) / 5;
  const barWidth = columnWidth * (weighted ? 0.3 : 0.5);

  const bars = CLASSES.map(index => {
    const x = PAD.left + columnWidth * (index + 0.5);
    const raw = (counts[index] / maximum) * plot;
    const winner = index === group.result_class ? " winner" : "";
    const left = weighted ? x - barWidth - 2 : x - barWidth / 2;
    let body = `<rect class="bar${winner}" x="${left}" y="${height - PAD.bottom - raw}" width="${barWidth}" height="${Math.max(0, raw)}"><title>Class ${index}: ${counts[index]} articles</title></rect>`;
    if (weighted) {
      const value = (weighted[index] / maximum) * plot;
      body += `<rect class="bar weighted" x="${x + 2}" y="${height - PAD.bottom - value}" width="${barWidth}" height="${Math.max(0, value)}"><title>Class ${index}: weight ${number(weighted[index], 3)}</title></rect>`;
    }
    return body;
  }).join("");

  const legend = weighted
    ? legendItem("bar", "Articles") + legendItem("bar weighted", "Weight this method counted")
    : "";

  return figure(
    "Class distribution",
    weighted
      ? "Articles per class, beside the weights this method counted."
      : "How many articles landed in each class.",
    width,
    height,
    gridlines(width, height, maximum) + bars + classAxis(width, height, columnWidth),
    legend,
  );
}

/**
 * The averaged probability vector. Its shape says something the winning class does
 * not: a flat profile means the model spread its belief, a spike means it did not.
 */
export function probabilityProfile(group) {
  const means = group.mean_probabilities;
  if (!Array.isArray(means)) {
    return note("This model stored only hard classes in the dataset, so there is no probability profile to plot.");
  }

  const width = 520;
  const height = 240;
  const plot = height - PAD.top - PAD.bottom;
  const columnWidth = (width - PAD.left - PAD.right) / 5;
  const maximum = Math.max(...means.map(Number), 0.2) * 1.15;

  const bars = CLASSES.map(index => {
    const value = (Number(means[index]) / maximum) * plot;
    const x = PAD.left + columnWidth * (index + 0.5) - columnWidth * 0.25;
    const winner = index === group.result_class ? " winner" : "";
    return `<rect class="bar${winner}" x="${x}" y="${height - PAD.bottom - value}" width="${columnWidth * 0.5}" height="${Math.max(0, value)}"><title>Class ${index}: ${percent(means[index])}</title></rect>
      <text class="axis value" x="${PAD.left + columnWidth * (index + 0.5)}" y="${height - PAD.bottom - value - 5}" text-anchor="middle">${percent(means[index])}</text>`;
  }).join("");

  // The centre of mass is where the "expected class" method reads its answer.
  const expectation = means.reduce((total, value, index) => total + index * Number(value), 0);
  const centreX = PAD.left + columnWidth * (expectation + 0.5);
  const centre = `<line class="marker" x1="${centreX}" y1="${PAD.top}" x2="${centreX}" y2="${height - PAD.bottom}"></line>
    <text class="axis marker-label" x="${centreX}" y="${PAD.top - 4}" text-anchor="middle">centre of mass ${number(expectation)}</text>`;

  return figure(
    "Mean probability profile",
    "The five probabilities averaged over the counted articles.",
    width,
    height,
    gridlines(width, height, maximum) + bars + centre + classAxis(width, height, columnWidth),
  );
}

/**
 * One mark per article, placed by its class and by how sure the model was.
 * A publisher with a high variance looks obviously different here from one whose
 * articles merely straddle a boundary, which a single number cannot convey.
 */
export function articleDispersion(group) {
  const articles = (group.articles || []).filter(item => !item.excluded);
  if (articles.length < 2) return note("At least two counted articles are needed for a dispersion plot.");

  const width = 520;
  const height = 240;
  const plot = height - PAD.top - PAD.bottom;
  const columnWidth = (width - PAD.left - PAD.right) / 5;
  const hasConfidence = articles.some(item => item.confidence !== null);
  // The vertical scale starts at 20%: with five classes that is the floor a softmax
  // maximum can reach, so plotting from zero would waste most of the height.
  const FLOOR = 0.2;

  const marks = articles.map((item, position) => {
    // Spread the marks of a class across its column so overlapping articles stay
    // countable; the horizontal offset carries no meaning of its own.
    const spread = ((position * 2654435761) % 1000) / 1000 - 0.5;
    const x = PAD.left + columnWidth * (item.predicted_class + 0.5) + spread * columnWidth * 0.7;
    const confidence = item.confidence === null ? 0.5 : Number(item.confidence);
    const y = height - PAD.bottom - ((confidence - FLOOR) / (1 - FLOOR)) * plot;
    const winner = item.predicted_class === group.result_class ? " winner" : "";
    const adjacent = Math.abs(item.predicted_class - group.result_class) === 1 ? " adjacent" : "";
    return `<circle class="mark${winner}${adjacent}" cx="${x}" cy="${Math.max(PAD.top, Math.min(height - PAD.bottom, y))}" r="3.5"><title>Class ${item.predicted_class}${item.confidence === null ? "" : `, confidence ${percent(item.confidence)}`}</title></circle>`;
  }).join("");

  const verdict = group.result_class === null ? "" : (() => {
    const x = PAD.left + columnWidth * (group.result_class + 0.5);
    return `<rect class="band" x="${x - columnWidth / 2}" y="${PAD.top}" width="${columnWidth}" height="${plot}"></rect>`;
  })();

  const ticks = hasConfidence
    ? [0.2, 0.4, 0.6, 0.8, 1].map(value => {
        const y = height - PAD.bottom - ((value - FLOOR) / (1 - FLOOR)) * plot;
        return `<line class="grid" x1="${PAD.left}" y1="${y}" x2="${width - PAD.right}" y2="${y}"></line>
          <text class="axis" x="${PAD.left - 6}" y="${y + 4}" text-anchor="end">${percent(value)}</text>`;
      }).join("")
    : "";
  const axis = hasConfidence
    ? `<text class="axis" transform="translate(12, ${PAD.top + plot / 2}) rotate(-90)" text-anchor="middle">Confidence</text>`
    : `<text class="axis" x="${PAD.left}" y="${PAD.top - 4}">Confidence not stored for this model, so every dot sits at mid-height.</text>`;

  return figure(
    "Article dispersion",
    "One dot per counted article: horizontal position is its class, vertical position how sure the model was.",
    width,
    height,
    ticks + verdict + marks + classAxis(width, height, columnWidth) + axis,
  );
}

/**
 * Where a publisher's variance sits against the risk bands, with the tolerant
 * variance beside it. Reading the two together is the point: a wide strict spread
 * that collapses once adjacent classes are allowed is a boundary case, not chaos.
 */
export function varianceGauge(group, bands) {
  if (group.variance === null || group.variance === undefined) {
    return note("No variance to show without a counted aggregate.");
  }

  const width = 520;
  const height = 150;
  const left = 30;
  const right = width - 30;
  // The scale stops at 3: the observed maximum across the shipped dataset is 3.55,
  // and everything past 2 is already deep in the worst band.
  const maximum = 3;
  const position = (value) => left + (Math.min(value, maximum) / maximum) * (right - left);

  // The open-ended top band carries no upper_bound at all, so `!= null` (which also
  // catches undefined) is what excludes it rather than a strict comparison.
  const cuts = [0, ...bands.map(entry => entry.upper_bound).filter(value => value != null), maximum];
  const segments = bands.map((entry, index) => {
    const from = position(cuts[index]);
    const to = position(cuts[index + 1]);
    return `<rect class="band-${escapeHtml(entry.band)}" x="${from}" y="44" width="${to - from}" height="22"><title>${escapeHtml(entry.description)}</title></rect>
      <text class="axis" x="${(from + to) / 2}" y="38" text-anchor="middle">${escapeHtml(entry.band)}</text>`;
  }).join("");

  const ticks = cuts.map(value =>
    `<text class="axis" x="${position(value)}" y="82" text-anchor="middle">${number(value, value % 1 === 0 ? 0 : 2)}</text>`
  ).join("");

  const needle = (value, label, className) => {
    const x = position(value);
    return `<g class="needle ${className}"><line x1="${x}" y1="40" x2="${x}" y2="70"></line>
      <text class="axis" x="${x}" y="${className === "strict" ? 104 : 120}" text-anchor="middle">${escapeHtml(label)} ${number(value, 3)}</text></g>`;
  };

  return figure(
    "Variance and risk band",
    "Class variance across the counted articles, against the error rates measured on the study corpus.",
    width,
    height,
    segments + ticks + needle(Number(group.variance), "variance", "strict") +
      needle(Number(group.tolerant_variance), "allowing adjacent classes", "tolerant"),
  );
}

/**
 * Every model's class distribution side by side. Two families agreeing is much
 * stronger evidence than either one alone, and disagreement is worth seeing plainly.
 */
export function modelComparison(groups) {
  const usable = groups.filter(group => group.result_class !== null);
  if (usable.length < 2) return note("At least two models with a verdict are needed for a comparison.");

  const width = 520;
  const height = 250;
  const plot = height - PAD.top - PAD.bottom;
  const columnWidth = (width - PAD.left - PAD.right) / 5;
  const slot = (columnWidth * 0.7) / usable.length;
  const shares = usable.map(group => {
    const total = CLASSES.reduce((sum, index) => sum + Number(group.class_counts[String(index)] || 0), 0) || 1;
    return CLASSES.map(index => Number(group.class_counts[String(index)] || 0) / total);
  });
  const maximum = Math.max(...shares.flat(), 0.2) * 1.15;

  const bars = usable.map((group, model) => CLASSES.map(index => {
    const value = (shares[model][index] / maximum) * plot;
    const x = PAD.left + columnWidth * (index + 0.5) - (columnWidth * 0.7) / 2 + slot * model;
    return `<rect class="bar series-${model % 4}" x="${x}" y="${height - PAD.bottom - value}" width="${Math.max(1, slot - 2)}" height="${Math.max(0, value)}"><title>${escapeHtml(group.display_name)} — class ${index}: ${percent(shares[model][index])}</title></rect>`;
  }).join("")).join("");

  const legend = usable
    .map((group, model) => legendItem(`bar series-${model % 4}`, `${group.display_name} → class ${group.result_class}`))
    .join("");

  return figure(
    "Model comparison",
    "Share of articles per class for each model, so agreement between families is visible at a glance.",
    width,
    height,
    gridlines(width, height, maximum, {format: "percent"}) + bars + classAxis(width, height, columnWidth),
    legend,
  );
}

/** Charts the user can pick between, in the order they are offered. */
export const CHART_TYPES = [
  {
    id: "class_distribution",
    label: "Class distribution",
    scope: "group",
    draw: (group) => classDistribution(group),
  },
  {
    id: "article_dispersion",
    label: "Article dispersion",
    scope: "group",
    draw: (group) => articleDispersion(group),
  },
  {
    id: "variance_gauge",
    label: "Variance and risk",
    scope: "group",
    draw: (group, context) => varianceGauge(group, context.bands),
  },
  {
    id: "probability_profile",
    label: "Probability profile",
    scope: "group",
    draw: (group) => probabilityProfile(group),
  },
  {
    id: "model_comparison",
    label: "Model comparison",
    scope: "payload",
    draw: (payload) => modelComparison(payload.models),
  },
];
