import type { Model, ModelGroup, SessionSummary, Snapshot } from './types';

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try { detail = JSON.parse(text).detail ?? text; } catch { /* Plain-text errors are valid. */ }
    throw new ApiError(String(detail), response.status);
  }
  return response.json() as Promise<T>;
}

const sessionPath = (id: string) => `/api/sessions/${encodeURIComponent(id)}`;
const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  ...(body === undefined ? {} : {
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
});

export const api = {
  sessions: (signal?: AbortSignal) => request<{ sessions: SessionSummary[] }>('/api/sessions', { signal }),
  models: (signal?: AbortSignal) => request<{ models: ModelGroup[] }>('/api/models', { signal }),
  createSession: () => request<{ id: string }>('/api/sessions', post()),
  deleteSession: (id: string) => request<{ deleted: boolean }>(sessionPath(id), { method: 'DELETE' }),
  snapshot: (id: string, signal?: AbortSignal) => request<Snapshot>(`${sessionPath(id)}/conversation`, { signal }),
  send: (id: string, content: string) => request<{ accepted: boolean }>(`${sessionPath(id)}/messages`, post({ content })),
  stop: (id: string) => request<{ stopped: boolean }>(`${sessionPath(id)}/control/stop`, post()),
  switchModel: (id: string, provider: string, model: string) =>
    request<{ model: Model }>(`${sessionPath(id)}/model`, post({ provider, model })),
  eventsUrl: (id: string) => `${sessionPath(id)}/events?after=0`,
};
