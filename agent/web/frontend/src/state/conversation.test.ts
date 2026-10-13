import { describe, expect, it } from 'vitest';
import type { AgentEvent, Snapshot } from '../api/types';
import { conversationReducer as reduce, emptyConversation, type Conversation } from './conversation';

const model = { provider: 'deepseek', name: 'deepseek-chat' };
const snapshot = (seq: number, busy = false): Snapshot => ({ id: 'test', seq, busy, model });
const start: AgentEvent = { seq: 1, type: 'turn.started', prompt: 'hello', runId: 'run' };
const modelStart: AgentEvent = { seq: 2, type: 'model.started', round: 0, runId: 'run' };
const text: AgentEvent = { seq: 3, type: 'message.delta', text: 'partial', round: 0, runId: 'run' };
const requested: AgentEvent = { seq: 4, type: 'tool.requested', tool: 'search', callId: 'call', arguments: { query: 'hello' } };
const completed: AgentEvent = { seq: 5, type: 'tool.completed', tool: 'search', callId: 'call', result: 'found' };

function replay(events: AgentEvent[], snap = snapshot(events.at(-1)?.seq ?? 0)): Conversation {
  return reduce(reduce(emptyConversation(), { type: 'snapshot', snapshot: snap }), { type: 'events', events });
}

describe('existing event protocol -> conversation', () => {
  it('restores partial output while the same turn is still running', () => {
    const view = replay([start, modelStart, text], snapshot(3, true));
    expect(view.ready).toBe(true);
    expect(view.busy).toBe(true);
    expect(view.items).toMatchObject([{ role: 'user', content: 'hello' }, { role: 'assistant', content: 'partial' }]);
    const next = reduce(view, { type: 'events', events: [{ ...text, seq: 4, text: ' answer' }] });
    expect(next.items[1]).toMatchObject({ content: 'partial answer' });
    expect(next.items).toHaveLength(2);
  });

  it('has identical output for batched history and individually received events', () => {
    const events: AgentEvent[] = [start, modelStart, text, requested, completed, { seq: 6, type: 'turn.completed' }];
    const initial = reduce(emptyConversation(), { type: 'snapshot', snapshot: snapshot(6) });
    const live = events.reduce((state, event) => reduce(state, { type: 'events', events: [event] }), initial);
    expect(live).toEqual(replay(events));
    expect(live.items[2]).toMatchObject({ name: 'search', result: 'found', status: 'completed' });
  });

  it('ignores duplicate and older records after an SSE reconnect', () => {
    const view = replay([start, modelStart, text], snapshot(3, true));
    expect(reduce(view, { type: 'events', events: [start, modelStart, text] })).toEqual(view);
  });

  it('marks unfinished old tools as interrupted when the runtime is idle', () => {
    const view = replay([start, modelStart, text, requested], snapshot(4, false));
    expect(view.busy).toBe(false);
    expect(view.items[2]).toMatchObject({ status: 'interrupted' });
    expect(view.items[1]).toMatchObject({ content: 'partial' });
  });

  it('does not finish loading or enable sending halfway through history replay', () => {
    const view = replay([start, modelStart], snapshot(4, true));
    expect(view.ready).toBe(false);
    const next = reduce(view, { type: 'events', events: [text, requested] });
    expect(next.ready).toBe(true);
    expect(next.busy).toBe(true);
  });

  it('does not apply an old snapshot to newer live events', () => {
    const view = replay([start, modelStart, text], snapshot(2, false));
    expect(view.ready).toBe(true);
    // The replay watermark was crossed at seq=2; a later live turn updates it.
    const next = reduce(view, { type: 'events', events: [{ seq: 4, type: 'turn.started', prompt: 'next' }] });
    expect(next.busy).toBe(true);
  });

  it('handles cancellation and failure without leaving running tool cards', () => {
    for (const event of [{ seq: 5, type: 'turn.cancelled' }, { seq: 5, type: 'turn.failed', reason: 'offline' }] as AgentEvent[]) {
      const view = replay([start, modelStart, text, requested, event]);
      expect(view.busy).toBe(false);
      expect(view.items[2]).toMatchObject({ status: 'interrupted' });
      if (event.type === 'turn.failed') expect(view.error).toBe('offline');
    }
  });

  it('starts a new assistant bubble after a tool round', () => {
    const view = replay([start, modelStart, text, requested, completed,
      { seq: 6, type: 'model.started', round: 1 },
      { seq: 7, type: 'message.delta', text: 'final', round: 1 },
      { seq: 8, type: 'turn.completed' }]);
    expect(view.items).toHaveLength(4);
    expect(view.items[3]).toMatchObject({ role: 'assistant', content: 'final' });
  });

  it('advances the cursor for supported events that have no UI yet', () => {
    const view = replay([start, { seq: 2, type: 'reasoning.delta' }], snapshot(2, true));
    expect(view.seq).toBe(2);
    expect(view.ready).toBe(true);
    expect(view.items).toHaveLength(1);
  });

  it('handles a new empty session and fully clears state on a session change', () => {
    expect(replay([]).ready).toBe(true);
    expect(reduce(replay([start, modelStart, text]), { type: 'reset' })).toEqual(emptyConversation());
  });
});
