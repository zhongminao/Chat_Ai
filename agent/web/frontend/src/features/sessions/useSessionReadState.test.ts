import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SessionSummary } from '../../api/types';
import { sessionIndicator, useSessionReadState } from './useSessionReadState';

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
let sessions: SessionSummary[];
let page: { visibilityState: string; hasFocus: () => boolean };
let focused: boolean;
let handlers: Map<string, () => void>;
function render(selected: string | null = 'one', ready = true, seq = 10) {
  hooks.index = 0;
  const value = useSessionReadState(sessions, selected, ready, seq);
  hooks.pending.splice(0).forEach(run => run());
  return value;
}

beforeEach(() => {
  hooks.values = []; hooks.effects = []; hooks.pending = [];
  sessions = [session]; focused = true; handlers = new Map();
  const events = {
    addEventListener: (type: string, handler: () => void) => handlers.set(type, handler),
    removeEventListener: (type: string) => handlers.delete(type),
  };
  page = { visibilityState: 'visible', hasFocus: () => focused };
  vi.stubGlobal('document', Object.assign(page, events));
  vi.stubGlobal('window', events);
});
afterEach(() => { hooks.effects.forEach(effect => effect?.cleanup?.()); vi.unstubAllGlobals(); });

describe('history session indicators', () => {
  it('defaults existing content to read and prioritizes running over unread outcomes', () => {
    expect(sessionIndicator(session)).toBeNull();
    expect(sessionIndicator({ ...session, status: 'failed' })).toBeNull();
    expect(sessionIndicator({ ...session, busy: true, status: 'failed' }, 10)).toBe('running');
    expect(sessionIndicator({ ...session, status: 'failed' }, 9)).toBe('failed');
    expect(sessionIndicator(session, 9)).toBe('unread');
    expect(sessionIndicator({ ...session, status: 'failed' }, 10)).toBeNull();
    expect(sessionIndicator({ ...session, status: 'cancelled' }, 10)).toBeNull();
    expect(sessionIndicator({ ...session, updatedAt: 999 }, 10)).toBeNull();
  });

  it('baselines asynchronously loaded history, then tracks only new activity while open', () => {
    sessions = [];
    render(null, false, 0);
    sessions = [session, { ...session, id: 'two', activitySeq: 20, status: 'failed' }];
    render(null, false, 0);
    expect(render(null, false, 0)).toEqual({ one: 10, two: 20 });
    sessions = sessions.map(item => item.id === 'two' ? { ...item, activitySeq: 21 } : item);
    render(null, false, 0);
    const cursors = render(null, false, 0);
    expect(cursors.two).toBe(20);
    expect(sessionIndicator(sessions[1], cursors.two)).toBe('failed');
    sessions = [...sessions, { ...session, id: 'new', activitySeq: 0 }];
    render(null, false, 0);
    expect(render(null, false, 0).new).toBe(0);
    sessions = sessions.map(item => item.id === 'new' ? { ...item, activitySeq: 1 } : item);
    expect(sessionIndicator(sessions[2], render(null, false, 0).new)).toBe('unread');
  });

  it('marks new content read only when loaded, visible and focused', () => {
    render('one', false);
    focused = false; handlers.get('blur')?.();
    render('one', true, 11);
    expect(render('one', true, 11)).toEqual({ one: 10 });
    focused = true; page.visibilityState = 'hidden'; handlers.get('visibilitychange')?.();
    render('one', true, 11);
    expect(render('one', true, 11)).toEqual({ one: 10 });
    page.visibilityState = 'visible'; handlers.get('visibilitychange')?.();
    render('one', false, 11);
    expect(render('one', false, 11)).toEqual({ one: 10 });
    render('one', true, 11);
    expect(render('one', true, 11)).toEqual({ one: 11 });
  });

  it('rebuilds the read baseline on reload rather than restoring stale unread state', () => {
    render(null, false, 0);
    sessions = [{ ...session, activitySeq: 15 }];
    expect(sessionIndicator(sessions[0], render(null, false, 0).one)).toBe('unread');
    hooks.effects.forEach(effect => effect?.cleanup?.());
    hooks.values = []; hooks.effects = []; hooks.pending = [];
    render(null, false, 0);
    const cursors = render(null, false, 0);
    expect(cursors).toEqual({ one: 15 });
    expect(sessionIndicator(sessions[0], cursors.one)).toBeNull();
  });
});
