import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import { useWatch } from './useWatch';

const hooks = vi.hoisted(() => ({ values: [] as unknown[], index: 0,
  effects: [] as { deps: unknown[]; cleanup?: () => void }[], pending: [] as (() => void)[] }));
vi.mock('react', () => ({
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => {
      hooks.values[index] = typeof value === 'function' ? value(hooks.values[index]) : value;
    }];
  },
  useRef(current: unknown) { return hooks.values[hooks.index++] ??= { current }; },
  useEffect(setup: () => (() => void), deps: unknown[]) {
    const index = hooks.index++;
    const previous = hooks.effects[index];
    if (previous && deps.every((value, i) => Object.is(value, previous.deps[i]))) return;
    const effect = hooks.effects[index] = { deps, cleanup: previous?.cleanup };
    hooks.pending.push(() => { effect.cleanup?.(); effect.cleanup = setup(); });
  },
}));
vi.mock('../../api/client', () => ({ api: { watch: vi.fn() } }));
const changed = vi.fn();
function render(id = 'parent') {
  hooks.index = 0;
  const view = useWatch(id, changed);
  hooks.pending.splice(0).forEach(run => run());
  return view;
}
beforeEach(() => {
  vi.useFakeTimers(); vi.resetAllMocks();
  hooks.values = []; hooks.effects = []; hooks.pending = [];
  vi.mocked(api.watch).mockImplementation(() => new Promise(() => {}));
});
afterEach(() => {
  hooks.effects.forEach(effect => effect?.cleanup?.());
  vi.useRealTimers();
});
it('recovers automatically with a fresh snapshot, removing stale agents and the error', async () => {
  vi.mocked(api.watch)
    .mockResolvedValueOnce({ cursor: 10, changes: [{ id: 'old', kind: 'agent', version: 10, status: 'running' }] })
    .mockRejectedValueOnce(new Error('offline'));
  render(); await vi.advanceTimersByTimeAsync(0);
  expect(render().error).toBe(true);
  expect(render().resources.map(item => item.id)).toEqual(['old']);
  vi.mocked(api.watch).mockResolvedValueOnce({ cursor: 1, changes: [] });
  await vi.advanceTimersByTimeAsync(1000);
  expect(render().error).toBe(false);
  expect(render().resources).toEqual([]);
  expect(vi.mocked(api.watch).mock.calls[2].slice(0, 3)).toEqual(['parent', undefined, 0]);
  expect(changed).toHaveBeenCalledTimes(2);
});
it('backs off repeated failures and cancels delayed retries on session change', async () => {
  vi.mocked(api.watch).mockRejectedValue(new Error('offline'));
  render(); await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(999); expect(api.watch).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1); expect(api.watch).toHaveBeenCalledTimes(2);
  await vi.advanceTimersByTimeAsync(1999); expect(api.watch).toHaveBeenCalledTimes(2);
  render('other'); await vi.advanceTimersByTimeAsync(0);
  vi.mocked(api.watch).mockImplementation(() => new Promise(() => {}));
  await vi.advanceTimersByTimeAsync(1000);
  expect(vi.mocked(api.watch).mock.calls.map(call => call[0])).toEqual(['parent', 'parent', 'other', 'other']);
});
it('does not apply a late response from a previous session', async () => {
  let resolve!: (value: { cursor: number; changes: [] }) => void;
  vi.mocked(api.watch).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  render(); render('other');
  resolve({ cursor: 100, changes: [] }); await vi.advanceTimersByTimeAsync(0);
  expect(render('other').resources).toEqual([]);
  expect(changed).not.toHaveBeenCalled();
});
