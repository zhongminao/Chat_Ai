import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import type { SessionSummary } from '../../api/types';
import { restoreSession } from './useSessions';

vi.mock('../../api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../../api/client')>();
  return { ...actual, api: { ...actual.api, createSession: vi.fn(), sessions: vi.fn() } };
});
const session = (id: string, changes: Partial<SessionSummary> = {}): SessionSummary => ({
  id, title: id, createdAt: null, updatedAt: 0, empty: false, busy: false, ...changes,
});
beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe('tab-local selection restoration without creating empty sessions', () => {
  it('restores saved nonempty history', () => {
    vi.stubGlobal('sessionStorage', { getItem: () => 'history' });
    expect(restoreSession([session('history', { busy: true })])).toBe('history');
    expect(api.sessions).not.toHaveBeenCalled();
    expect(api.createSession).not.toHaveBeenCalled();
  });
  it.each([null, 'deleted', 'empty'])('opens the local draft for saved selection %s', saved => {
    vi.stubGlobal('sessionStorage', { getItem: () => saved });
    expect(restoreSession([session('history'), session('empty', { empty: true })])).toBeNull();
    expect(api.sessions).not.toHaveBeenCalled();
    expect(api.createSession).not.toHaveBeenCalled();
  });
  it('opens the local draft when browser storage is unavailable', () => {
    vi.stubGlobal('sessionStorage', { getItem: () => { throw new Error('blocked'); } });
    expect(restoreSession([])).toBeNull();
    expect(api.createSession).not.toHaveBeenCalled();
  });
});
