import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SessionSummary } from '../../api/types';
import { readSessionCursors, sessionIndicator, useSessionReadState } from './useSessionReadState';

const hooks = vi.hoisted(() => ({
  values: [] as unknown[], index: 0,
  effects: [] as { deps: unknown[]; cleanup?: () => void }[], pending: [] as (() => void)[],
}));
vi.mock('react', () => ({
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = typeof initial === 'function' ? initial() : initial;
    return [hooks.values[index], (value: unknown) => {
      hooks.values[index] = typeof value === 'function' ? value(hooks.values[index]) : value;
    }];
  },
  useEffect(setup: () => void | (() => void), deps: unknown[]) {
    const index = hooks.index++;
    const previous = hooks.effects[index];
    if (previous && deps.every((value, i) => Object.is(value, previous.deps[i]))) return;
    const effect = hooks.effects[index] = { deps, cleanup: previous?.cleanup };
    hooks.pending.push(() => { effect.cleanup?.(); effect.cleanup = setup() || undefined; });
  },
}));

const session: SessionSummary = { id: 'one', title: 'One', createdAt: null, updatedAt: 0, activitySeq: 10, status: 'idle' };
let page: { visibilityState: string; hasFocus: () => boolean };
let focused: boolean;
let handlers: Map<string, () => void>;
let store: Map<string, string>;
function render(selected = 'one', ready = true, seq = 10) {
  hooks.index = 0;
  const value = useSessionReadState(selected, ready, seq);
  hooks.pending.splice(0).forEach(run => run());
  return value;
}

beforeEach(() => {
  hooks.values = []; hooks.effects = []; hooks.pending = [];
  focused = true; handlers = new Map(); store = new Map();
  const events = {
    addEventListener: (type: string, handler: () => void) => handlers.set(type, handler),
    removeEventListener: (type: string) => handlers.delete(type),
  };
  page = { visibilityState: 'visible', hasFocus: () => focused };
  vi.stubGlobal('document', Object.assign(page, events));
  vi.stubGlobal('window', events);
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, value); },
  });
});
afterEach(() => { hooks.effects.forEach(effect => effect?.cleanup?.()); vi.unstubAllGlobals(); });

describe('history session indicators', () => {
  it('prioritizes running, unread failure and ordinary unread, hiding read outcomes', () => {
    expect(sessionIndicator({ ...session, busy: true, status: 'failed' }, 10)).toBe('running');
    expect(sessionIndicator({ ...session, status: 'failed' }, 9)).toBe('failed');
    expect(sessionIndicator(session, 9)).toBe('unread');
    expect(sessionIndicator({ ...session, status: 'failed' }, 10)).toBeNull();
    expect(sessionIndicator({ ...session, status: 'cancelled' }, 10)).toBeNull();
    expect(sessionIndicator({ ...session, updatedAt: 999 }, 10)).toBeNull();
    expect(sessionIndicator({ ...session, activitySeq: 0 })).toBeNull();
  });

  it('marks only a ready, visible and focused conversation as read', () => {
    render('one', false);
    expect(render('one', false)).toEqual({});
    focused = false; handlers.get('blur')?.();
    render();
    expect(render()).toEqual({});
    focused = true; page.visibilityState = 'hidden'; handlers.get('visibilitychange')?.();
    render();
    expect(render()).toEqual({});
    page.visibilityState = 'visible'; handlers.get('visibilitychange')?.();
    render();
    expect(render()).toEqual({ one: 10 });
    expect(readSessionCursors()).toEqual({ one: 10 });
    render('two', true, 20);
    expect(render('two', true, 20)).toEqual({ one: 10, two: 20 });
  });

  it('preserves read cursors across reloads and tolerates unavailable storage', () => {
    render();
    hooks.values = []; hooks.effects = []; hooks.pending = [];
    expect(render()).toEqual({ one: 10 });
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } });
    expect(readSessionCursors()).toEqual({});
    render('one', true, 11);
    expect(render('one', true, 11)).toEqual({ one: 11 });
  });
});
