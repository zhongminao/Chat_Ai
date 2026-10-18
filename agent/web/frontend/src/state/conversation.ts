import type { AgentEvent, ImageAsset, Model, SessionState } from '../api/types';

export type TextItem = { id: string; kind: 'text'; role: 'user' | 'assistant'; content: string; images?: string[];
  guidance?: 'queued' | 'applied' | 'undelivered' };
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
  session: SessionState | null;
  execution: { startIndex: number; startedAt?: number } | null;
}

export const emptyConversation = (): Conversation => ({
  items: [], images: [], seq: 0, assistantId: null, busy: false, ready: false,
  model: null, error: null, session: null, execution: null,
});

export type Action =
  | { type: 'reset' }
  | { type: 'initialize'; session: SessionState }
  | { type: 'ready'; seq: number }
  | { type: 'disconnected' }
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
      if (event.seq > (state.session?.seq ?? 0)) next.images = upsertImage(state.images, event.image);
      break;
    case 'guidance.queued':
      next.items = [...state.items, { id: `guidance:${event.messageId}`, kind: 'text', role: 'user',
        content: event.content, images: event.images?.map(image => image.id), guidance: 'queued' }];
      break;
    case 'guidance.applied': {
      const index = state.items.findIndex(item => item.id === `guidance:${event.messageId}`);
      next.items = state.items.map(item => item.id === `guidance:${event.messageId}` && item.kind === 'text'
        ? { ...item, guidance: 'applied' } : item);
      if (index >= 0) next.execution = { startIndex: index + 1, startedAt: event.time };
      next.assistantId = null;
      break;
    }
    case 'guidance.undelivered':
      next.items = state.items.map(item => item.id === `guidance:${event.messageId}` && item.kind === 'text'
        ? { ...item, guidance: 'undelivered' } : item);
      break;
    case 'model.started': next.assistantId = null; break;
    case 'context.compaction.started':
      next.assistantId = null;
      next.items = appendExecution(state.items, { id: `context:${event.compactionId}`, kind: 'context', status: 'running' });
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
        : appendExecution(state.items, { id, kind: 'text', role: 'assistant', content: event.text });
      break;
    }
    case 'tool.requested':
      if (event.tool === 'submit') break;
      next.items = appendExecution(state.items, { id: `tool:${event.callId}`, kind: 'tool', name: event.tool,
        arguments: event.arguments, status: 'running' });
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
        : appendExecution(state.items, { id, kind: 'tool', name: event.tool, result: event.result, images, status });
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
      if (event.seq > (state.session?.seq ?? 0) || !next.images.some(entry => entry.id === image.id)) {
        next.images = upsertImage(next.images, image);
      }
    }
  }
  return next;
}

function appendExecution(items: Item[], item: Item): Item[] {
  const index = items.findIndex(entry => entry.kind === 'text' && entry.guidance === 'queued');
  return index < 0 ? [...items, item] : [...items.slice(0, index), item, ...items.slice(index)];
}

function interruptPending(items: Item[]): Item[] {
  return items.map(item => item.kind === 'text' && item.guidance === 'queued' ? { ...item, guidance: 'undelivered' }
    : (item.kind === 'tool' || item.kind === 'context') && item.status === 'running' ? { ...item, status: 'interrupted' } : item);
}

export function conversationReducer(state: Conversation, action: Action): Conversation {
  switch (action.type) {
    case 'reset': return emptyConversation();
    case 'initialize': return { ...(action.session.reset ? emptyConversation() : state),
      session: action.session, ready: false, model: action.session.model,
      images: action.session.images ?? [], busy: action.session.busy };
    case 'ready': {
      if (!state.session || action.seq !== state.session.seq || state.seq < action.seq) return state;
      const busy = state.seq === action.seq ? state.session.busy : state.busy;
      return { ...state, ready: true, busy,
        model: state.seq === action.seq ? state.session.model : state.model,
        items: busy ? state.items : interruptPending(state.items) };
    }
    case 'disconnected': return { ...state, ready: false };
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
