import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import { useSessions } from './useSessions';

const states = vi.hoisted(() => [] as ReturnType<typeof vi.fn>[]);
vi.mock('react', () => ({
  useState: () => { const update = vi.fn(); states.push(update); return [null, update]; },
  useRef: (current: unknown) => ({ current }),
  useCallback: (callback: unknown) => callback,
  useEffect: vi.fn(),
}));
vi.mock('../../api/client', async original => {
  const actual = await original<typeof import('../../api/client')>();
  return { ...actual, api: { ...actual.api, models: vi.fn(), sessions: vi.fn() } };
});
beforeEach(() => { states.length = 0; vi.clearAllMocks(); });

describe('manual model refresh', () => {
  it('preserves old choices until data arrives and coalesces repeated clicks', async () => {
    const groups = [{ provider: 'local', displayName: 'Local', models: [{ id: 'qwen', name: 'Qwen', enabled: true }] }];
    const defaultModel = { provider: 'gpt', name: 'gpt-6.1-sol' };
    let finish!: (value: { models: typeof groups; defaultModel: typeof defaultModel }) => void;
    vi.mocked(api.models).mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const hook = useSessions();
    const pending = hook.refreshModels();
    await hook.refreshModels();
    expect(api.models).toHaveBeenCalledOnce();
    expect(states.flatMap(state => state.mock.calls.map(call => call[0]))).not.toContain(groups);
    finish({ models: groups, defaultModel });
    await pending;
    expect(states.some(state => state.mock.calls.some(call => call[0] === defaultModel))).toBe(true);
    expect(states.some(state => state.mock.calls.some(call => call[0] === groups))).toBe(true);
    expect(api.sessions).not.toHaveBeenCalled();
  });

  it('reports failure without clearing choices and allows retry', async () => {
    vi.mocked(api.models).mockRejectedValueOnce(new Error('network error')).mockResolvedValue({ models: [], defaultModel: { provider: 'gpt', name: 'gpt-6.1-sol' } });
    const hook = useSessions();
    await hook.refreshModels();
    expect(states.some(state => state.mock.calls.some(call => call[0] === 'network error'))).toBe(true);
    expect(states.flatMap(state => state.mock.calls.map(call => call[0])).some(Array.isArray)).toBe(false);
    await hook.refreshModels();
    expect(api.models).toHaveBeenCalledTimes(2);
    expect(api.sessions).not.toHaveBeenCalled();
  });
});
