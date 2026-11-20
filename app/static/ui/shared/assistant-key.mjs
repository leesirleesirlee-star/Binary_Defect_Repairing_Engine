/**
 * Minimal client for the local assistant-key API.
 * The provider key is accepted only over the local session and is never stored
 * by the browser; this module only carries it to the backend once.
 */
const VERSION_HEADER = 'X-BinaryRepair-Contract-Version';
const VERSION = '1';

let tokenPromise = null;

async function sessionToken() {
  tokenPromise ??= (async () => {
    const response = await fetch('/api/session', {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {Accept: 'application/json', [VERSION_HEADER]: VERSION},
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body?.session !== true || typeof body.csrf_token !== 'string') {
      throw Object.assign(new Error(body?.detail || 'The local session is unavailable.'), {
        status: response.status,
        code: body?.code,
      });
    }
    return body.csrf_token;
  })().catch(error => {
    tokenPromise = null;
    throw error;
  });
  return tokenPromise;
}

async function call(path, {method = 'GET', body, allowFailure = false} = {}) {
  const headers = {Accept: 'application/json'};
  if (method !== 'GET') headers['x-csrf-token'] = await sessionToken();
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok && !allowFailure) {
    throw Object.assign(new Error(payload?.detail || response.statusText), {
      status: response.status,
      code: payload?.code,
      body: payload,
    });
  }
  if (response.status === 401) tokenPromise = null;
  return payload;
}

export const assistantKey = {
  status: () => call('/api/assistant/key'),
  save: key => call('/api/assistant/key', {method: 'POST', body: {key}}),
  test: model => call('/api/assistant/key/test', {method: 'POST', allowFailure: true,
    body: model ? {model} : undefined}),
  clear: () => call('/api/assistant/key', {method: 'DELETE'}),
};
