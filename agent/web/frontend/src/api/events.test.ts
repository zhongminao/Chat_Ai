import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { subscribe } from './events';
import type { AgentEvent, SessionState } from './types';

class FakeEventSource {
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  close = vi.fn(() => { this.readyState = 2; });
  constructor(public url: string) { FakeEventSource.instances.push(this); }
  emit(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }); }
}

const initial: SessionState & { type: string } = {
  type: 'session.init', id: 'test', seq: 2, after: 0, reset: false,
  busy: true, model: { provider: 'local', name: 'test' }, images: [],
};
const first: AgentEvent = { type: 'turn.started', seq: 1, prompt: 'hello' };
const second: AgentEvent = { type: 'message.delta', seq: 2, text: 'hi', round: 0 };

function listen(after = 0) {
  const handlers = { initialize: vi.fn(), ready: vi.fn(), events: vi.fn(), connection: vi.fn(), error: vi.fn() };
  const close = subscribe('test', handlers, after);
  return { source: FakeEventSource.instances.at(-1)!, handlers, close };
}

beforeEach(() => {
  vi.useFakeTimers(); FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('SSE session protocol', () => {
  it('subscribes after an HTTP history snapshot', () => {
    const { source, close } = listen(42);
    expect(source.url).toBe('/api/sessions/test/events?after=42');
    close();
  });
  it('uses one EventSource and flushes history before the ready control frame', () => {
    const { source, handlers, close } = listen();
    source.onopen?.(); source.emit(initial); source.emit(first); source.emit(second);
    expect(handlers.events).not.toHaveBeenCalled();
    source.emit({ type: 'session.ready', seq: 2 });
    expect(source.url).toBe('/api/sessions/test/events?after=0');
    expect(handlers.initialize).toHaveBeenCalledWith(initial);
    expect(handlers.events).toHaveBeenCalledExactlyOnceWith([first, second]);
    expect(handlers.events.mock.invocationCallOrder[0]).toBeLessThan(handlers.ready.mock.invocationCallOrder[0]);
    vi.advanceTimersByTime(100);
    expect(handlers.events).toHaveBeenCalledOnce();
    close();
  });

  it('continues rendering live deltas in short batches after replay', () => {
    const { source, handlers, close } = listen(1);
    source.emit({ ...initial, after: 1, seq: 1 }); source.emit({ type: 'session.ready', seq: 1 }); source.emit(second);
    vi.advanceTimersByTime(32);
    expect(handlers.events).toHaveBeenCalledExactlyOnceWith([second]);
    close();
  });

  it('flushes received events on disconnect and reinitializes the same EventSource on reconnect', () => {
    const { source, handlers, close } = listen();
    source.emit(initial); source.emit(first); source.onerror?.();
    expect(handlers.events).toHaveBeenCalledWith([first]);
    expect(handlers.connection).toHaveBeenLastCalledWith(false);
    expect(handlers.error).not.toHaveBeenCalled();
    source.onopen?.();
    source.emit({ ...initial, after: 1, busy: false });
    source.emit(second); source.emit({ type: 'session.ready', seq: 2 });
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(handlers.initialize).toHaveBeenCalledTimes(2);
    expect(handlers.events).toHaveBeenLastCalledWith([second]);
    close();
  });

  it('rejects malformed initialization and invalid sequence numbers', () => {
    const { source, handlers, close } = listen();
    source.emit({ ...initial, id: 'other' });
    source.emit({ ...initial, after: 9 });
    source.emit({ ...first, seq: -1 });
    expect(handlers.error).toHaveBeenCalledOnce();
    expect(handlers.initialize).not.toHaveBeenCalled();
    expect(handlers.events).not.toHaveBeenCalled();
    close();
  });

  it('rejects a gap without acknowledging the missing event', () => {
    const { source, handlers, close } = listen(2);
    source.emit({ ...initial, after: 2 });
    source.emit({ ...second, seq: 4 });
    expect(handlers.events).not.toHaveBeenCalled();
    expect(handlers.error).toHaveBeenCalledWith('会话事件不连续，请重新打开会话');
    expect(source.close).toHaveBeenCalled();
    close();
  });

  it('rejects a server cursor ahead of actually handled events', () => {
    const { source, handlers, close } = listen(2);
    source.emit({ ...initial, after: 3, seq: 3 });
    expect(handlers.initialize).not.toHaveBeenCalled();
    expect(handlers.error).toHaveBeenCalledWith('会话续传游标跳跃，请重新打开会话');
    close();
  });

  it('reports permanent connection closure and cancels queued rendering on cleanup', () => {
    const { source, handlers, close } = listen();
    source.readyState = 2; source.onerror?.();
    expect(handlers.error).toHaveBeenCalledOnce();
    source.emit(first); close(); vi.runAllTimers();
    expect(source.close).toHaveBeenCalled();
    expect(handlers.events).not.toHaveBeenCalled();
  });
});
