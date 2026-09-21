/**
 * The status button in the top bar and the workspace overview it opens.
 *
 * This is the only part of the interface that lives outside the routed content
 * area, so it manages its own elements and listeners.
 */

import {api} from "./api.js";
import {errorCard} from "./components.js";
import {escapeHtml} from "./format.js";

const stateBadge = document.querySelector("#system-state");
const systemPopover = document.querySelector("#system-popover");

/** Say whether the service can reach the network, for the badge in the top bar.
 *
 * The badge answers one question: can I classify a new article right now? That
 * depends on network retrieval, not on where the instance is running, so it
 * reports "online" or "offline" and says nothing about local versus published.
 * The offline branch is load-bearing rather than cosmetic: strict offline mode
 * cannot fetch a page, so the badge must never claim to be online when the
 * service is not actually reaching the network.
 */
function instanceLabel(status) {
  return status.offline ? "Ready · offline" : "Ready · online";
}

/** Show whether the backend is reachable, and what kind of instance it is. */
async function refreshSystemBadge() {
  try {
    const status = await api("/api/v1/status");
    stateBadge.textContent = instanceLabel(status);
    return status;
  } catch (error) {
    stateBadge.textContent = "Status unavailable";
    return null;
  }
}

/** Fill the popover with the current ledger, dataset and runtime counts. */
async function loadSystemPopover() {
  systemPopover.innerHTML = `<div class="loading">Loading overview…</div>`;
  try {
    const status = await api("/api/v1/status");
    const ledgers = status.ledger_counts;
    const derived = status.derived_counts;
    systemPopover.innerHTML = `
      <div class="popover-section">
        <div class="popover-row"><span>Articles</span><b>${Number(derived.articles).toLocaleString()}</b></div>
        <div class="popover-row"><span>Stored predictions</span><b>${Number(derived.historical_predictions).toLocaleString()}</b></div>
        <div class="popover-row"><span>Publishers</span><b>${Number(derived.publishers).toLocaleString()}</b></div>
        <div class="popover-row"><span>Model identities</span><b>${Number(ledgers.models).toLocaleString()}</b></div>
      </div>
      <div class="popover-section">
        <div class="popover-row"><span>Device</span><b>${escapeHtml(status.device)}</b></div>
        <div class="popover-row"><span>Schema</span><b>${escapeHtml(status.schema_version)}</b></div>
        <div class="popover-row"><span>Version</span><b>${escapeHtml(status.application_version)}</b></div>
      </div>
      <a class="popover-link" href="#models">Manage models →</a>`;
  } catch (error) {
    systemPopover.innerHTML = errorCard(error.message);
  }
}

function closeSystemPopover() {
  if (systemPopover.hidden) return;
  systemPopover.hidden = true;
  stateBadge.setAttribute("aria-expanded", "false");
}

async function toggleSystemPopover() {
  const opening = systemPopover.hidden;
  systemPopover.hidden = !opening;
  stateBadge.setAttribute("aria-expanded", String(opening));
  if (opening) await loadSystemPopover();
}

/** Wire up the badge and start showing the backend status. */
export function initTopbar() {
  stateBadge.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleSystemPopover();
  });
  // A click anywhere else, Escape, or navigating away all dismiss the popover.
  document.addEventListener("click", (event) => {
    if (!systemPopover.hidden && !systemPopover.contains(event.target) && event.target !== stateBadge) {
      closeSystemPopover();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !systemPopover.hidden) {
      closeSystemPopover();
      stateBadge.focus();
    }
  });
  window.addEventListener("hashchange", closeSystemPopover);
  refreshSystemBadge();
}
