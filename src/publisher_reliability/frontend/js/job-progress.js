/** Progress bar for the background jobs the user starts from a page. */

import {api} from "./api.js";
import {humanizePhase} from "./format.js";

const POLL_INTERVAL_MS = 700;
const JOB_TIMEOUT_MS = 480000;

/** Determinate progress bar labelled with the job's current phase. */
export const progressCard = (phase, percent) => {
  const clamped = Math.max(0, Math.min(100, Number(percent) || 0));
  return `<div class="progress-card" aria-live="polite">
    <div class="progress-message"><span>${humanizePhase(phase)}…</span><b>${clamped}%</b></div>
    <div class="progress-track"><span style="width:${clamped}%"></span></div>
  </div>`;
};

/**
 * Poll a job until it finishes, redrawing `output` with its progress.
 * Resolves with the finished job, or throws with the backend's failure message.
 */
export async function waitForJob(jobId, output) {
  const deadline = Date.now() + JOB_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const job = await api(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
    output.innerHTML = progressCard(job.phase || job.status, job.progress);
    if (job.status === "succeeded") return job;
    if (job.status === "failed") throw new Error(job.error_message || "Model scan failed.");
    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  throw new Error("This job is still running; inspect it on the Jobs page.");
}
