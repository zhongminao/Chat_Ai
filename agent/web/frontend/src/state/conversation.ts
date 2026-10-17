import type { AgentEvent, ImageAsset, Model, ConversationSnapshot } from '../api/types';

export type TextItem = { id: string; kind: 'text'; role: 'user' | 'assistant'; content: string; images?: string[] };
export type ToolItem = { id: string; kind: 'tool'; name: string; arguments?: unknown; result?: unknown; images?: string[]; status: 'running' | 'completed' | 'interrupted' | 'rejected' };
export type ExecutionItem = TextItem | ToolItem;
export type ContextCompactionItem = { id: string; kind: 'context'; status: 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'; reason?: string };
export type ReportItem = { id: string; kind: 'report'; content: string; process: ExecutionItem[]; durationSeconds: number | null };
export type Item = ExecutionItem | ReportItem | ContextCompactionItem;
export interface Conversation {
  items: Item[];
  images: ImageAsset[];
  seq: number;
  assistantId: string | null;
  busy: boolean;
  ready: boolean;
  model: Model | null;
  error: string | null;
  snapshot: ConversationSnapshot | null;
  execution: { startIndex: number; startedAt?: number } | null;
}

export const emptyConversation = (): Conversation => ({
  items: [], images: [], seq: 0, assistantId: null, busy: false, ready: false,
  model: null, error: null, snapshot: null, execution: null,
});

export type Action =
  | { type: 'reset' }
  | { type: 'snapshot'; snapshot: ConversationSnapshot }
  | { type: 'events'; events: AgentEvent[] }
  | { type: 'busy'; busy: boolean }
  | { type: 'model'; model: Model }
  | { type: 'image'; image: ImageAsset }
  | { type: 'error'; error: string | null };

function applyEvent(state: Conversation, event: AgentEvent): Conversation {
  if (event.seq <= state.seq) return state;
  let next = { ...state, seq: event.seq };
  switch (event.type) {
    case 'turn.started':
      next = { ...next, busy: true, assistantId: null, error: null,
        execution: { startIndex: state.items.length + 1, startedAt: event.time },
        items: [...state.items, { id: `user:${event.seq}`, kind: 'text', role: 'user', content: event.prompt,
          images: event.images?.map(image => image.id) }] };
      break;
    case 'image.renamed':
      if (event.seq > (state.snapshot?.seq ?? 0)) next.images = upsertImage(state.images, event.image);
      break;
    case 'model.started': next.assistantId = null; break;
    case 'context.compaction.started':
      next.assistantId = null;
      next.items = [...state.items, { id: `context:${event.compactionId}`, kind: 'context', status: 'running' }];
      break;
    case 'context.compacted':
    case 'context.compaction.failed':
    case 'context.compaction.cancelled': {
      const id = `context:${event.compactionId}`;
      const item: ContextCompactionItem = { id, kind: 'context',
        status: event.type === 'context.compacted' ? 'completed' : event.type === 'context.compaction.failed' ? 'failed' : 'cancelled',
        reason: event.type === 'context.compaction.failed' ? event.reason : undefined };
      next.items = state.items.some(entry => entry.id === id)
        ? state.items.map(entry => entry.id === id ? item : entry) : [...state.items, item];
      break;
    }
    case 'message.delta': {
      const id = state.assistantId ?? `assistant:${event.seq}`;
      const exists = state.items.some(item => item.id === id);
      next.assistantId = id;
      next.items = exists
        ? state.items.map(item => item.id === id && item.kind === 'text' ? { ...item, content: item.content + event.text } : item)
        : [...state.items, { id, kind: 'text', role: 'assistant', content: event.text }];
      break;
    }
    case 'tool.requested':
      if (event.tool === 'submit') break;
      next.items = [...state.items, { id: `tool:${event.callId}`, kind: 'tool', name: event.tool,
        arguments: event.arguments, status: 'running' }];
      break;
    case 'tool.completed': {
      if (event.tool === 'submit') break;
      const id = `tool:${event.callId}`;
      const exists = state.items.some(item => item.id === id);
      const result = String(event.result);
      const status = result.startsWith('[tool cancelled]') ? 'interrupted' : result.startsWith('[tool denied]') ? 'rejected' : 'completed';
      const images = event.images?.map(image => image.id);
      next.items = exists
        ? state.items.map(item => item.id === id && item.kind === 'tool' ? { ...item, result: event.result, images: images ?? item.images, status } : item)
        : [...state.items, { id, kind: 'tool', name: event.tool, result: event.result, images, status }];
      break;
    }
    case 'report.submitted': {
      const startIndex = state.execution?.startIndex ?? state.items.length;
      const startedAt = state.execution?.startedAt;
      next.items = [...state.items.slice(0, startIndex),
        ...state.items.slice(startIndex).filter(item => item.kind === 'context'), {
        id: `report:${event.seq}`, kind: 'report', content: event.content,
        process: state.items.slice(startIndex).filter((item): item is ExecutionItem => item.kind === 'text' || item.kind === 'tool'),
        durationSeconds: startedAt !== undefined && event.time !== undefined
          ? Math.max(0, Math.floor((event.time - startedAt) / 1e9)) : null,
      }];
      next.execution = null;
      next.assistantId = null;
      break;
    }
    case 'model.changed': next.model = event.new; break;
    case 'turn.failed':
    case 'error':
      next.error = event.type === 'turn.failed' ? event.reason : event.reason ?? event.message;
      // Failed and cancelled runs cannot leave a tool card marked as running.
      next.items = interruptPending(state.items);
      next.busy = false; next.assistantId = null; next.execution = null;
      break;
    case 'turn.cancelled':
      next.items = interruptPending(state.items);
      next.busy = false; next.assistantId = null; next.execution = null;
      break;
    case 'turn.completed': next.busy = false; next.assistantId = null; break;
  }
  if ('images' in event) {
    for (const image of event.images ?? []) {
      if (event.seq > (state.snapshot?.seq ?? 0) || !next.images.some(entry => entry.id === image.id)) {
        next.images = upsertImage(next.images, image);
      }
    }
  }
  // Replay existing events before admitting new input. The snapshot is the
  // authority on whether an old unfinished run is still executing in-process.
  if (!state.ready && state.snapshot && next.seq >= state.snapshot.seq) {
    next.ready = true;
    next.model = state.snapshot.model;
    if (next.seq === state.snapshot.seq) next.busy = state.snapshot.busy;
    if (!next.busy) {
      next.items = interruptPending(next.items);
    }
  }
  return next;
}

function interruptPending(items: Item[]): Item[] {
  return items.map(item => (item.kind === 'tool' || item.kind === 'context') && item.status === 'running'
    ? { ...item, status: 'interrupted' } : item);
}

export function conversationReducer(state: Conversation, action: Action): Conversation {
  switch (action.type) {
    case 'reset': return emptyConversation();
    case 'snapshot': return { ...emptyConversation(), snapshot: action.snapshot,
      model: action.snapshot.model, images: action.snapshot.images ?? [],
      busy: action.snapshot.busy, ready: action.snapshot.seq === 0 };
    case 'events': return action.events.reduce(applyEvent, state);
    case 'busy': return { ...state, busy: action.busy };
    case 'model': return { ...state, model: action.model };
    case 'image': return { ...state, images: upsertImage(state.images, action.image) };
    case 'error': return { ...state, error: action.error };
  }
}

function upsertImage(images: ImageAsset[], image: ImageAsset): ImageAsset[] {
  return images.some(entry => entry.id === image.id)
    ? images.map(entry => entry.id === image.id ? image : entry)
    : [...images, image];
}
