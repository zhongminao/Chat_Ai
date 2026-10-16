import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../../api/client';
import type { SessionSummary } from '../../api/types';
import { findOrCreateEmptySession } from './useSessions';

vi.mock('../../api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../../api/client')>();
  return { ...actual, api: { ...actual.api, getConversationSnapshot: vi.fn(), createSession: vi.fn(), sessions: vi.fn() } };
});

const session = (id: string, changes: Partial<SessionSummary> = {}): SessionSummary => ({
  id, title: id, createdAt: null, updatedAt: 0, empty: true, busy: false, ...changes,
});
const empty = (id: string) => ({ id, seq: 0, busy: false, model: { provider: 'test', name: 'test' }, messages: [] });

beforeEach(() => { vi.resetAllMocks(); });

describe('default new conversation and new-session selection', () => {
  it('opens an empty session on first load without reading historical conversations', async () => {
    vi.mocked(api.getConversationSnapshot).mockResolvedValue(empty('empty'));
    expect(await findOrCreateEmptySession([session('history', { empty: false }), session('empty')])).toBe('empty');
    expect(api.getConversationSnapshot).toHaveBeenCalledExactlyOnceWith('empty');
    expect(api.createSession).not.toHaveBeenCalled();
    expect(api.sessions).not.toHaveBeenCalled();
  });

  it('creates directly from known summaries without waiting for another list query', async () => {
    vi.mocked(api.createSession).mockResolvedValue({ id: 'new' });
    expect(await findOrCreateEmptySession([session('history', { empty: false }), session('busy', { busy: true }),
      session('child', { parent_session_id: 'parent' })])).toBe('new');
    expect(api.createSession).toHaveBeenCalledOnce();
    expect(api.sessions).not.toHaveBeenCalled();
    expect(api.getConversationSnapshot).not.toHaveBeenCalled();
  });

  it('prefers the selected empty session so repeated clicks reuse it', async () => {
    vi.mocked(api.getConversationSnapshot).mockResolvedValue(empty('selected'));
    expect(await findOrCreateEmptySession([session('other'), session('selected')], 'selected')).toBe('selected');
    expect(api.getConversationSnapshot).toHaveBeenCalledExactlyOnceWith('selected');
  });

  it('checks stale candidates and skips sessions deleted by another client', async () => {
    vi.mocked(api.getConversationSnapshot).mockRejectedValueOnce(new ApiError('gone', 404))
      .mockResolvedValueOnce({ ...empty('used'), messages: [{ role: 'user', content: 'hello' }] })
      .mockResolvedValueOnce(empty('available'));
    expect(await findOrCreateEmptySession([session('gone'), session('used'), session('available')])).toBe('available');
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it('surfaces connection errors without creating duplicate empty sessions', async () => {
    vi.mocked(api.getConversationSnapshot).mockRejectedValue(new ApiError('offline', 503));
    await expect(findOrCreateEmptySession([session('empty')])).rejects.toThrow('offline');
    expect(api.createSession).not.toHaveBeenCalled();
  });
});
