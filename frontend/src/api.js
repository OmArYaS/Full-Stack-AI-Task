/**
 * Thin API client for the FastAPI backend.
 *
 * All network access is to a local backend (no paid/cloud services). The base
 * URL is configurable via VITE_API_BASE_URL and falls back to the Vite proxy.
 */

const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  let response;
  try {
    response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch (err) {
    throw new Error(`Cannot reach backend at ${url}: ${err.message}`);
  }

  const isJson = (response.headers.get('content-type') || '').includes('json');
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      payload && typeof payload === 'object'
        ? payload.message || payload.detail || JSON.stringify(payload)
        : payload;
    const error = new Error(message || `Request failed (${response.status})`);
    error.status = response.status;
    error.code = payload && payload.error;
    throw error;
  }
  return payload;
}

export const api = {
  health: () => request('/health'),

  createTask: ({ inputText, schema, maxRetries }) =>
    request('/api/tasks', {
      method: 'POST',
      body: JSON.stringify({
        input_text: inputText,
        ...(schema ? { schema } : {}),
        ...(maxRetries !== undefined && maxRetries !== null
          ? { max_retries: Number(maxRetries) }
          : {}),
      }),
    }),

  listTasks: (status) =>
    request(`/api/tasks${status ? `?status=${encodeURIComponent(status)}` : ''}`),

  getTask: (taskId) => request(`/api/tasks/${encodeURIComponent(taskId)}`),

  reviewTask: (taskId, { decision, fields, notes, reviewer }) =>
    request(`/api/tasks/${encodeURIComponent(taskId)}/review`, {
      method: 'PATCH',
      body: JSON.stringify({ decision, fields, notes, reviewer }),
    }),

  exportTasks: (format, status) => {
    const params = new URLSearchParams({ fmt: format });
    if (status) params.set('status', status);
    return `${BASE}/api/tasks/export?${params.toString()}`;
  },

  metrics: () => request('/api/metrics'),
};
