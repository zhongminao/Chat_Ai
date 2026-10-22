import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../../api/client';
import type { SessionSummary } from '../../api/types';
import { findOrCreateEmptySession, restoreOrCreateSession } from './useSessions';

vi.mock('../../api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../../api/client')>();
  return { ...actual, api: { ...actual.api, createSession: vi.fn(), sessions: vi.fn() } };
});

const session = (id: string, changes: Partial<SessionSummary> = {}): SessionSummary => ({
  id, title: id, createdAt: null, updatedAt: 0, empty: true, busy: false, ...changes,
});

beforeEach(() => { vi.resetAllMocks(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe('tab-local conversation restoration', () => {
  it('restores saved running history without fetching another conversation', async () => {
    vi.stubGlobal('sessionStorage', { getItem: () => 'history' });
    expect(await restoreOrCreateSession([session('history', { empty: false, busy: true })])).toBe('history');
    expect(api.sessions).not.toHaveBeenCalled();
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it('opens an empty session in a fresh tab using summaries only', async () => {
    vi.stubGlobal('sessionStorage', { getItem: () => null });
    vi.mocked(api.sessions).mockResolvedValue({ sessions: [session('empty')] });
    expect(await restoreOrCreateSession([session('history', { empty: false }), session('empty')])).toBe('empty');
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it('creates an empty session when the saved selection was deleted', async () => {
    vi.stubGlobal('sessionStorage', { getItem: () => 'deleted' });
    vi.mocked(api.createSession).mockResolvedValue({ id: 'new' });
    expect(await restoreOrCreateSession([session('history', { empty: false })])).toBe('new');
    expect(api.sessions).not.toHaveBeenCalled();
  });

  it('still opens a conversation when browser storage is unavailable', async () => {
    vi.stubGlobal('sessionStorage', { getItem: () => { throw new Error('blocked'); } });
    vi.mocked(api.createSession).mockResolvedValue({ id: 'new' });
    expect(await restoreOrCreateSession([])).toBe('new');
  });
});

describe('empty session reuse without snapshot queries', () => {
  it('prefers the selected empty session after revalidating its summary', async () => {
    vi.mocked(api.sessions).mockResolvedValue({ sessions: [session('other'), session('selected')] });
    expect(await findOrCreateEmptySession([session('other'), session('selected')], 'selected')).toBe('selected');
    expect(api.sessions).toHaveBeenCalledOnce();
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it('creates directly when summaries contain no reusable session', async () => {
    vi.mocked(api.createSession).mockResolvedValue({ id: 'new' });
    expect(await findOrCreateEmptySession([session('history', { empty: false }), session('busy', { busy: true }),
      session('archived', { archived: true }), session('child', { parent_session_id: 'parent' })])).toBe('new');
    expect(api.sessions).not.toHaveBeenCalled();
  });

  it('skips stale deleted, used and running candidates using fresh summaries', async () => {
    vi.mocked(api.sessions).mockResolvedValue({ sessions: [session('used', { empty: false }),
      session('running', { busy: true }), session('available')] });
    expect(await findOrCreateEmptySession([session('deleted'), session('used'), session('available')])).toBe('available');
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it('creates a replacement when all empty candidates disappeared', async () => {
    vi.mocked(api.sessions).mockResolvedValue({ sessions: [] });
    vi.mocked(api.createSession).mockResolvedValue({ id: 'new' });
    expect(await findOrCreateEmptySession([session('deleted')])).toBe('new');
  });

  it('surfaces connection failures without creating duplicate sessions', async () => {
    vi.mocked(api.sessions).mockRejectedValue(new ApiError('offline', 503));
    await expect(findOrCreateEmptySession([session('empty')])).rejects.toThrow('offline');
    expect(api.createSession).not.toHaveBeenCalled();
  });
});
