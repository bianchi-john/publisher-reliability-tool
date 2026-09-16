/**
 * The only place that talks to the backend.
 *
 * Requests belong to the page currently on screen: the router opens a scope before
 * rendering, and opening the next one aborts whatever the previous page left in
 * flight, so a slow response can never overwrite a newer view.
 */

let scope = null;

/** Abort the previous page's requests and open a scope for the next one. */
export function openRequestScope() {
  scope?.abort();
  scope = new AbortController();
  return scope;
}

/** True while `controller` is still the scope the router is rendering. */
export function isActiveScope(controller) {
  return scope === controller;
}

/**
 * Call the local API and return the parsed JSON body.
 *
 * Errors carry the backend's own message when it sent one, so pages can show it
 * to the user without inspecting status codes.
 */
export async function api(path, options = {}) {
  const requestOptions = {...options};
  if (!requestOptions.signal && scope) {
    requestOptions.signal = scope.signal;
  }
  const response = await fetch(path, requestOptions);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error?.message || `Request failed (${response.status})`);
  return body;
}
