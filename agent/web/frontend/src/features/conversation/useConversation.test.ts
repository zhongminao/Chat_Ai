import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import { subscribe } from '../../api/events';
import { conversationReducer } from '../../state/conversation';
import { useConversation } from './useConversation';

const hooks = vi.hoisted(() => ({
  values: [] as unknown[], index: 0,
  effects: [] as { deps?: unknown[]; cleanup?: () => void }[],
  pending: [] as (() => void)[],
}));
vi.mock('react', () => ({
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => {
      hooks.values[index] = typeof value === 'function' ? value(hooks.values[index]) : value;
    }];
  },
  useRef(current: unknown) {
    const index = hooks.index++;
    return hooks.values[index] ??= { current };
  },
  useReducer(reducer: (value: number) => number, initial: number) {
    const index = hooks.index++;
    hooks.values[index] ??= initial;
    return [hooks.values[index], () => { hooks.values[index] = reducer(hooks.values[index] as number); }];
  },
  useEffect(setup: () => (() => void), deps: unknown[]) {
    const index = hooks.index++;
    const previous = hooks.effects[index];
    if (previous && deps.every((value, position) => Object.is(value, previous.deps?.[position]))) return;
    const effect = hooks.effects[index] = { deps, cleanup: previous?.cleanup };
    hooks.pending.push(() => { effect.cleanup?.(); effect.cleanup = setup(); });
  },
}));
vi.mock('../../api/client', () => ({ api: { history: vi.fn() } }));
vi.mock('../../api/events', () => ({ subscribe: vi.fn(() => vi.fn()) }));
vi.mock('../../state/conversation', async original => {
  const actual = await original<typeof import('../../state/conversation')>();
  return { ...actual, conversationReducer: vi.fn(actual.conversationReducer) };
});

function render(id: string) {
  hooks.index = 0;
  return useConversation(id, () => {});
}
function effects() { hooks.pending.splice(0).forEach(run => run()); }

beforeEach(() => {
  hooks.effects.forEach(effect => effect?.cleanup?.());
  hooks.values = []; hooks.effects = []; hooks.pending = [];
  vi.clearAllMocks();
  vi.mocked(api.history).mockResolvedValue({
    events: [{ type: 'turn.started', seq: 1, prompt: 'hello' }, { type: 'message.delta', seq: 2, text: 'old', round: 0 }],
    snapshot_seq: 2, min_seq: 1, has_more: false,
  });
});

describe('conversation view ownership', () => {
  it('reduces each SSE batch once and exposes the resulting view', async () => {
    render('one'); effects(); await Promise.resolve();
    const handlers = vi.mocked(subscribe).mock.calls[0][1];
    vi.mocked(conversationReducer).mockClear();
    handlers.events([{ type: 'message.delta', seq: 3, text: '+new', round: 0 }]);
    expect(conversationReducer).toHaveBeenCalledTimes(1);
    const view = render('one');
    expect(view.seq).toBe(3);
    expect(view.items.at(-1)).toMatchObject({ kind: 'text', content: 'old+new' });
  });

  it('retains the latest batch when switching tabs before React renders it', async () => {
    render('one'); effects(); await Promise.resolve();
    vi.mocked(subscribe).mock.calls[0][1].events([{ type: 'message.delta', seq: 3, text: '+latest', round: 0 }]);
    render('two'); effects(); await Promise.resolve();
    render('one'); effects();
    const view = render('one');
    expect(view.seq).toBe(3);
    expect(view.items.at(-1)).toMatchObject({ kind: 'text', content: 'old+latest' });
    expect(api.history).toHaveBeenCalledTimes(2);
    expect(vi.mocked(subscribe).mock.calls.at(-1)?.[2]).toBe(3);
  });
});
