import { describe, expect, it } from 'vitest';
import type { AgentEvent, SessionState } from '../api/types';
import { conversationReducer as reduce, emptyConversation, type Conversation } from './conversation';

const model = { provider: 'deepseek', name: 'deepseek-chat' };
const initialState = (seq: number, busy = false): SessionState => ({ id: 'test', seq, after: 0, reset: false, busy, model });
const start: AgentEvent = { seq: 1, type: 'turn.started', prompt: 'hello', runId: 'run' };
const modelStart: AgentEvent = { seq: 2, type: 'model.started', round: 0, runId: 'run' };
const text: AgentEvent = { seq: 3, type: 'message.delta', text: 'partial', round: 0, runId: 'run' };
const requested: AgentEvent = { seq: 4, type: 'tool.requested', tool: 'search', callId: 'call', arguments: { query: 'hello' } };
const completed: AgentEvent = { seq: 5, type: 'tool.completed', tool: 'search', callId: 'call', result: 'found' };

function replay(events: AgentEvent[], snap = initialState(events.at(-1)?.seq ?? 0)): Conversation {
  const view = reduce(reduce(emptyConversation(), { type: 'initialize', session: snap }), { type: 'events', events });
  return reduce(view, { type: 'ready', seq: snap.seq });
}

describe('existing event protocol -> conversation', () => {
  it('waits for explicit replay completion, including empty history', () => {
    const empty = reduce(emptyConversation(), { type: 'initialize', session: initialState(0) });
    expect(empty.ready).toBe(false);
    expect(reduce(empty, { type: 'ready', seq: 0 }).ready).toBe(true);
    const partial = reduce(emptyConversation(), { type: 'initialize', session: initialState(3) });
    expect(reduce(partial, { type: 'ready', seq: 3 }).ready).toBe(false);
  });

  it('retains messages across reconnect and corrects a restarted runtime at the same seq', () => {
    const view = replay([start, modelStart, text, requested], initialState(4, true));
    const disconnected = reduce(view, { type: 'disconnected' });
    expect(disconnected.ready).toBe(false);
    const resumed = reduce(disconnected, { type: 'initialize', session: { ...initialState(4), after: 4 } });
    expect(resumed.items).toEqual(view.items);
    expect(resumed.ready).toBe(false);
    const ready = reduce(resumed, { type: 'ready', seq: 4 });
    expect(ready.ready).toBe(true);
    expect(ready.busy).toBe(false);
    expect(ready.items[2]).toMatchObject({ status: 'interrupted' });
  });

  it('deduplicates replay after reconnect and preserves partial assistant text', () => {
    const view = replay([start, modelStart, text], initialState(3, true));
    const resumed = reduce(view, { type: 'initialize', session: { ...initialState(5), after: 3 } });
    const caughtUp = reduce(resumed, { type: 'events', events: [text, { ...text, seq: 4, text: ' rest' },
      { seq: 5, type: 'turn.completed' }] });
    expect(caughtUp.ready).toBe(false);
    const ready = reduce(caughtUp, { type: 'ready', seq: 5 });
    expect(ready.items).toHaveLength(2);
    expect(ready.items[1]).toMatchObject({ content: 'partial rest' });
    expect(reduce(ready, { type: 'events', events: [text] })).toEqual(ready);
  });

  it('clears stale state only when the server resets an ahead cursor', () => {
    const view = replay([start, modelStart, text], initialState(3, true));
    const reset = reduce(view, { type: 'initialize', session: { ...initialState(1), reset: true } });
    expect(reset.items).toEqual([]);
    expect(reset.seq).toBe(0);
    expect(reduce(reduce(reset, { type: 'events', events: [start] }), { type: 'ready', seq: 1 }).ready).toBe(true);
  });

  it('keeps current image names and selected model while replaying older metadata', () => {
    const image = { id: 'img', name: 'latest', ordinal: 1, filename: 'x.png', mime: 'image/png', width: 1, height: 1, size: 1 };
    const selected = { provider: 'local', name: 'selected' };
    const view = replay([{ ...start, images: [{ ...image, name: 'old' }] },
      { seq: 2, type: 'image.renamed', image: { ...image, name: 'older' } },
      { seq: 3, type: 'model.changed', new: model }], { ...initialState(3), model: selected, images: [image] });
    expect(view.images[0].name).toBe('latest');
    expect(view.model).toEqual(selected);
  });
  it('shows accepted guidance while the earlier assistant and complete tool batch keep updating above it', () => {
    const queued: AgentEvent = { seq: 4, type: 'guidance.queued', messageId: 'g', content: 'new requirements' };
    const view = replay([start, modelStart, text, queued,
      { ...text, seq: 5, text: ' continues' }, { ...requested, seq: 6 }, { ...completed, seq: 7 }], initialState(7, true));
    expect(view.items).toMatchObject([{ role: 'user' }, { role: 'assistant', content: 'partial continues' },
      { kind: 'tool', status: 'completed' }, { role: 'user', content: 'new requirements', guidance: 'queued' }]);
    const next = reduce(view, { type: 'events', events: [
      { seq: 8, type: 'guidance.applied', messageId: 'g', content: 'new requirements' },
      { seq: 9, type: 'model.started', round: 1 }, { ...text, seq: 10, round: 1, text: 'guided response' },
      { seq: 11, type: 'report.submitted', content: 'revised report' }, { seq: 12, type: 'turn.completed' },
    ] });
    expect(next.items).toMatchObject([{ role: 'user' }, { role: 'assistant' }, { kind: 'tool' },
      { role: 'user', content: 'new requirements', guidance: 'applied' }, { kind: 'report', content: 'revised report' }]);
  });

  it('marks accepted but unapplied guidance undelivered after cancellation or restart', () => {
    const queued: AgentEvent = { seq: 3, type: 'guidance.queued', messageId: 'g', content: 'not yet delivered' };
    expect(replay([start, modelStart, queued], initialState(3, false)).items[1]).toMatchObject({ guidance: 'undelivered' });
    const view = replay([start, modelStart, queued, { seq: 4, type: 'guidance.undelivered', messageId: 'g' },
      { seq: 5, type: 'turn.cancelled' }]);
    expect(view.items[1]).toMatchObject({ role: 'user', content: 'not yet delivered', guidance: 'undelivered' });
  });
  it('keeps rejected operations distinct from executed tools on replay', () => {
    const view = replay([start, requested, { ...completed, result: '[tool denied] 用户拒绝本次操作' }]);
    expect(view.items[1]).toMatchObject({ status: 'rejected' });
  });
  it('restores partial output while the same turn is still running', () => {
    const view = replay([start, modelStart, text], initialState(3, true));
    expect(view.ready).toBe(true);
    expect(view.busy).toBe(true);
    expect(view.items).toMatchObject([{ role: 'user', content: 'hello' }, { role: 'assistant', content: 'partial' }]);
    const next = reduce(view, { type: 'events', events: [{ ...text, seq: 4, text: ' answer' }] });
    expect(next.items[1]).toMatchObject({ content: 'partial answer' });
    expect(next.items).toHaveLength(2);
  });

  it('has identical output for batched history and individually received events', () => {
    const events: AgentEvent[] = [start, modelStart, text, requested, completed, { seq: 6, type: 'turn.completed' }];
    const initial = reduce(emptyConversation(), { type: 'initialize', session: initialState(6) });
    const live = reduce(events.reduce((state, event) => reduce(state, { type: 'events', events: [event] }), initial), { type: 'ready', seq: 6 });
    expect(live).toEqual(replay(events));
    expect(live.items[2]).toMatchObject({ name: 'search', result: 'found', status: 'completed' });
  });

  it('ignores duplicate and older records after an SSE reconnect', () => {
    const view = replay([start, modelStart, text], initialState(3, true));
    expect(reduce(view, { type: 'events', events: [start, modelStart, text] })).toEqual(view);
  });

  it('marks unfinished old tools as interrupted when the runtime is idle', () => {
    const view = replay([start, modelStart, text, requested], initialState(4, false));
    expect(view.busy).toBe(false);
    expect(view.items[2]).toMatchObject({ status: 'interrupted' });
    expect(view.items[1]).toMatchObject({ content: 'partial' });
  });

  it('does not finish loading or enable sending halfway through history replay', () => {
    const view = replay([start, modelStart], initialState(4, true));
    expect(view.ready).toBe(false);
    const next = reduce(view, { type: 'events', events: [text, requested] });
    expect(next.ready).toBe(false);
    expect(reduce(next, { type: 'ready', seq: 4 }).ready).toBe(true);
    expect(next.busy).toBe(true);
  });

  it('does not apply an old initialState to newer live events', () => {
    const view = replay([start, modelStart, text], initialState(2, false));
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
    const view = replay([start, { seq: 2, type: 'reasoning.delta' }], initialState(2, true));
    expect(view.seq).toBe(2);
    expect(view.ready).toBe(true);
    expect(view.items).toHaveLength(1);
  });

  it('keeps a submit reminder internal and leaves the original turn running', () => {
    const view = replay([start, modelStart, text,
      { seq: 4, type: 'completion.reminded', content: 'Call submit with the final report.' }], initialState(4, true));
    expect(view.seq).toBe(4);
    expect(view.busy).toBe(true);
    expect(view.error).toBeNull();
    expect(view.items).toMatchObject([{ role: 'user', content: 'hello' }, { role: 'assistant', content: 'partial' }]);
    expect(view.items).toHaveLength(2);
  });

  it('handles a new empty session and fully clears state on a session change', () => {
    expect(replay([]).ready).toBe(true);
    expect(reduce(replay([start, modelStart, text]), { type: 'reset' })).toEqual(emptyConversation());
  });

  it('replays context progress and keeps the completed marker outside submitted process', () => {
    const events: AgentEvent[] = [start,
      { seq: 2, type: 'context.compaction.started', compactionId: 'compact', beforeTokens: 33000 },
      { seq: 3, type: 'context.compacted', compactionId: 'compact', beforeTokens: 33000, afterTokens: 9000 },
      { ...modelStart, seq: 4 }, { ...text, seq: 5 },
      { seq: 6, type: 'report.submitted', content: 'final' }, { seq: 7, type: 'turn.completed' }];
    const view = replay(events);
    expect(view.items).toMatchObject([{ role: 'user' }, { kind: 'context', status: 'completed' },
      { kind: 'report', content: 'final', process: [{ kind: 'text', content: 'partial' }] }]);
    const live = reduce(events.reduce((state, event) => reduce(state, { type: 'events', events: [event] }),
      reduce(emptyConversation(), { type: 'initialize', session: initialState(7) })), { type: 'ready', seq: 7 });
    expect(live).toEqual(view);
    expect(reduce(view, { type: 'events', events })).toEqual(view);
  });

  it('shows active compression only while running and settles interrupted replay', () => {
    const progress: AgentEvent = { seq: 2, type: 'context.compaction.started', compactionId: 'compact', beforeTokens: 33000 };
    expect(replay([start, progress], initialState(2, true)).items[1]).toMatchObject({ status: 'running' });
    expect(replay([start, progress], initialState(2, false)).items[1]).toMatchObject({ status: 'interrupted' });
    for (const ending of [
      { seq: 3, type: 'context.compaction.cancelled', compactionId: 'compact' },
      { seq: 3, type: 'context.compaction.failed', compactionId: 'compact', reason: 'invalid summary' },
    ] as AgentEvent[]) {
      const view = replay([start, progress, ending]);
      expect(view.items[1]).toMatchObject({ status: ending.type === 'context.compaction.cancelled' ? 'cancelled' : 'failed' });
    }
  });

  it('renders submit as one report without a duplicate tool card, including replay', () => {
    const events: AgentEvent[] = [start, modelStart,
      { seq: 3, type: 'tool.requested', callId: 'submit', tool: 'submit', arguments: { content: '# Result' } },
      { seq: 4, type: 'tool.completed', callId: 'submit', tool: 'submit', result: 'Report submitted.' },
      { seq: 5, type: 'report.submitted', content: '# Result' },
      { seq: 6, type: 'turn.completed' }];
    const view = replay(events);
    expect(view.items).toEqual([
      expect.objectContaining({ kind: 'text', role: 'user' }),
      expect.objectContaining({ kind: 'report', content: '# Result' }),
    ]);
    expect(reduce(view, { type: 'events', events })).toEqual(view);
    expect(view.busy).toBe(false);
  });

  it('folds model and tool loops into the submitted answer using the full execution duration', () => {
    const view = replay([
      { ...start, time: 1e9 }, modelStart, text, requested, completed,
      { seq: 6, type: 'model.started', round: 1 },
      { seq: 7, type: 'message.delta', text: 'done', round: 1 },
      { seq: 8, type: 'report.submitted', content: '# Result', time: 66e9 },
      { seq: 9, type: 'turn.completed' },
    ]);
    expect(view.items).toHaveLength(2);
    expect(view.items[1]).toMatchObject({ kind: 'report', content: '# Result', durationSeconds: 65,
      process: [{ content: 'partial' }, { name: 'search', result: 'found' }, { content: 'done' }] });
  });

  it('keeps a manually requested background-result response in its own user turn', () => {
    const view = replay([
      start, modelStart, text, { seq: 4, type: 'turn.completed' },
      { seq: 5, type: 'turn.started', prompt: '处理后台任务', time: 10e9 },
      { seq: 6, type: 'model.started', round: 0 },
      { seq: 7, type: 'message.delta', text: 'reading report', round: 0 },
      { seq: 8, type: 'report.submitted', content: 'result', time: 12e9 },
      { seq: 9, type: 'turn.completed' },
    ]);
    expect(view.items).toHaveLength(4);
    expect(view.items[1]).toMatchObject({ content: 'partial' });
    expect(view.items[2]).toMatchObject({ role: 'user', content: '处理后台任务' });
    expect(view.items[3]).toMatchObject({ content: 'result', durationSeconds: 2, process: [{ content: 'reading report' }] });
  });
});


describe('bounded history and live event merging', () => {
  it('restores a cached view without deleting its loaded older history, then catches up', () => {
    const page = { events: [{ ...start, seq: 10 }, { ...text, seq: 11 }],
      snapshot_seq: 11, min_seq: 10, has_more: true };
    const cached = reduce(emptyConversation(), { type: 'history', page });
    const restored = reduce(cached, { type: 'restore', view: cached });
    expect(restored.items).toEqual(cached.items);
    expect(restored.ready).toBe(false);
    expect(restored.session).toBeNull();
    expect(restored.snapshotSeq).toBe(11);
    const fresh = reduce(restored, { type: 'initialize', session: { ...initialState(12), after: 11 } });
    const caughtUp = reduce(fresh, { type: 'events', events: [{ seq: 12, type: 'turn.completed' }] });
    expect(reduce(caughtUp, { type: 'ready', seq: 12 }).ready).toBe(true);
    expect(caughtUp.items).toEqual(cached.items);
  });

  it('opens a recent page at a nonzero seq and accepts the next SSE event', () => {
    const page = { events: [{ ...start, seq: 10 }, { ...text, seq: 11 }], snapshot_seq: 11,
      min_seq: 10, has_more: true };
    const recent = reduce(emptyConversation(), { type: 'history', page });
    expect(recent.items).toMatchObject([{ role: 'user' }, { content: 'partial' }]);
    expect(recent.seq).toBe(11);
    const active = reduce(recent, { type: 'events', events: [{ ...text, seq: 12, text: ' live' }] });
    expect(active.items[1]).toMatchObject({ content: 'partial live' });
    expect(active.minSeq).toBe(10);
  });

  it('joins a page after its snapshot with newer live events and retains metadata', () => {
    const selected = { provider: 'local', name: 'latest' };
    const recent = { events: [{ ...start, seq: 10 }, { ...text, seq: 11 }],
      snapshot_seq: 11, min_seq: 10, has_more: true };
    let view = reduce(emptyConversation(), { type: 'history', page: recent });
    view = reduce(view, { type: 'initialize', session: { ...initialState(13, false), after: 11, model: selected } });
    view = reduce(view, { type: 'events', events: [
      { ...text, seq: 12, text: ' next' }, { seq: 13, type: 'turn.completed' },
    ] });
    view = reduce(view, { type: 'ready', seq: 13 });
    const older = { events: [{ ...start, seq: 8 }, { seq: 9, type: 'turn.completed' as const }],
      snapshot_seq: 11, min_seq: 8, has_more: true };
    const joined = reduce(view, { type: 'history', page: older, older: true });
    expect(joined.minSeq).toBe(8);
    expect(joined.seq).toBe(13);
    expect(joined.ready).toBe(true);
    expect(joined.busy).toBe(false);
    expect(joined.model).toEqual(selected);
    expect(joined.items.at(-1)).toMatchObject({ content: 'partial next' });
  });

  it('rebuilds older pages once with the same report renderer while preserving live deltas', () => {
    const recent = { events: [{ ...start, seq: 10 }, { ...text, seq: 11 }],
      snapshot_seq: 11, min_seq: 10, has_more: true };
    let view = reduce(emptyConversation(), { type: 'history', page: recent });
    view = reduce(view, { type: 'events', events: [{ ...text, seq: 12, text: ' live' }] });
    const older = { events: [{ ...start, seq: 6 }, { seq: 7, type: 'report.submitted' as const, content: 'old report' },
      { seq: 8, type: 'turn.completed' as const }, { seq: 9, type: 'model.changed' as const, new: model }],
      snapshot_seq: 11, min_seq: 6, has_more: true };
    const joined = reduce(view, { type: 'history', page: older, older: true });
    expect(joined.items[1]).toMatchObject({ kind: 'report', content: 'old report' });
    expect(joined.items.at(-1)).toMatchObject({ content: 'partial live' });
    expect(joined.seq).toBe(12);
    expect(joined.minSeq).toBe(6);
    expect(reduce(joined, { type: 'events', events: [{ ...text, seq: 12 }] })).toEqual(joined);
    expect(reduce(joined, { type: 'history', page: older, older: true })).toEqual(joined);
  });
});
