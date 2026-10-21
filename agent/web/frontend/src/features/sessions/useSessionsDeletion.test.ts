import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../../api/client';
import type { SessionSummary } from '../../api/types';
import { useSessions } from './useSessions';

// Keep hook state between renders; startup effects stay off for these command tests.
const hooks = vi.hoisted(() => ({ values: [] as unknown[], index: 0 }));
vi.mock('react', () => ({
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => {
      hooks.values[index] = typeof value === 'function' ? value(hooks.values[index]) : value;
    }];
  },
  useRef: (value: unknown) => ({ current: value }),
  useCallback: (callback: unknown) => callback,
  useEffect: () => {},
}));

vi.mock('../../api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('../../api/client')>();
  return { ...actual, api: { ...actual.api, deleteSession: vi.fn(), createSession: vi.fn(), sessions: vi.fn() } };
});

const session = (id: string, changes: Partial<SessionSummary> = {}): SessionSummary => ({
  id, title: id, createdAt: null, updatedAt: 0, empty: false, busy: false, ...changes,
});
const parent = session('parent');
const child = session('child', { parent_session_id: parent.id });
const other = session('other', { empty: true });

function render() {
  hooks.index = 0;
  return useSessions();
}

beforeEach(() => {
  vi.resetAllMocks();
  hooks.values = [[parent, child, other], [], child.id];
  vi.stubGlobal('window', { confirm: vi.fn(() => true) });
  vi.stubGlobal('sessionStorage', { setItem: vi.fn(), removeItem: vi.fn() });
  vi.mocked(api.deleteSession).mockResolvedValue({ deleted: true });
  vi.mocked(api.sessions).mockResolvedValue({ sessions: [other] });
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('deleting a conversation with child sessions', () => {
  it('explains the scope and does nothing when confirmation is cancelled', async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    await render().remove(parent.id);
    const text = vi.mocked(window.confirm).mock.calls[0][0];
    for (const word of ['子会话', '聊天记录', '图片', '报告', '无法恢复', '先停止']) expect(text).toContain(word);
    expect(api.deleteSession).not.toHaveBeenCalled();
    expect(render().sessions).toEqual([parent, child, other]);
    expect(render().selected).toBe(child.id);
  });

  it('sends one deletion and leaves a deleted child view for an empty session', async () => {
    await render().remove(parent.id);
    expect(api.deleteSession).toHaveBeenCalledExactlyOnceWith(parent.id);
    expect(render().sessions).toEqual([other]);
    expect(render().selected).toBe(other.id);
    expect(sessionStorage.removeItem).toHaveBeenCalledWith('chat-ai:selected-session');
    expect(sessionStorage.setItem).toHaveBeenLastCalledWith('chat-ai:selected-session', other.id);
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it('preserves the current unrelated conversation', async () => {
    hooks.values[2] = other.id;
    await render().remove(parent.id);
    expect(render().selected).toBe(other.id);
    expect(render().sessions).toEqual([other]);
    expect(sessionStorage.removeItem).not.toHaveBeenCalled();
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it('keeps the conversation and child view when the backend requires stopping', async () => {
    vi.mocked(api.deleteSession).mockRejectedValue(new ApiError('主会话或子任务正在运行，请先停止后再删除。', 409));
    await render().remove(parent.id);
    expect(render().sessions).toEqual([parent, child, other]);
    expect(render().selected).toBe(child.id);
    expect(render().error).toContain('请先停止');
    expect(api.sessions).not.toHaveBeenCalled();
    expect(sessionStorage.removeItem).not.toHaveBeenCalled();
  });
});
