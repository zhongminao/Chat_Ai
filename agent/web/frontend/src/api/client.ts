import type { ImageAsset, Model, ModelGroup, SessionSummary, ConversationSnapshot, WatchResult } from './types';
import type { AccessMode, ApprovalSnapshot } from './types';

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
  approvals: (id: string, signal?: AbortSignal) => request<ApprovalSnapshot>(`${sessionPath(id)}/approvals`, { signal }),
  decideApproval: (id: string, approval: string, approved: boolean) => request<ApprovalSnapshot>(
    `${sessionPath(id)}/approvals/${encodeURIComponent(approval)}`, post({ approved })),
  accessMode: (id: string, mode: AccessMode) => request<ApprovalSnapshot>(`${sessionPath(id)}/access`, post({ mode })),
  sessions: (signal?: AbortSignal) => request<{ sessions: SessionSummary[] }>('/api/sessions', { signal }),
  watch: (id: string, cursor?: number, timeout = 0, signal?: AbortSignal) => request<WatchResult>(
    `${sessionPath(id)}/watch?timeout=${timeout}${cursor === undefined ? '' : `&cursor=${cursor}`}`, { signal }),
  models: (signal?: AbortSignal) => request<{ models: ModelGroup[] }>('/api/models', { signal }),
  createSession: () => request<{ id: string }>('/api/sessions', post()),
  deleteSession: (id: string) => request<{ deleted: boolean }>(sessionPath(id), { method: 'DELETE' }),
  renameSession: (id: string, title: string) => request<{ id: string; title: string }>(
    sessionPath(id), { ...post({ title }), method: 'PATCH' },
  ),
  getConversationSnapshot: (id: string, signal?: AbortSignal) => request<ConversationSnapshot>(`${sessionPath(id)}/conversation`, { signal }),
  send: (id: string, content: string, images: string[] = []) => request<{ accepted: boolean }>(`${sessionPath(id)}/messages`, post({ content, images })),
  uploadImage: (id: string, file: File) => {
    const body = new FormData(); body.append('file', file);
    return request<{ image: ImageAsset }>(`${sessionPath(id)}/images`, { method: 'POST', body });
  },
  renameImage: (id: string, image: string, name: string) => request<{ image: ImageAsset }>(
    `${sessionPath(id)}/images/${encodeURIComponent(image)}`,
    { ...post({ name }), method: 'PATCH' },
  ),
  imageUrl: (id: string, image: string, preview = false) =>
    `${sessionPath(id)}/images/${encodeURIComponent(image)}/content${preview ? '?preview=true' : ''}`,
  stop: (id: string) => request<{ stopped: boolean }>(`${sessionPath(id)}/control/stop`, post()),
  switchModel: (id: string, provider: string, model: string) =>
    request<{ model: Model }>(`${sessionPath(id)}/model`, post({ provider, model })),
  eventsUrl: (id: string) => `${sessionPath(id)}/events?after=0`,
};
