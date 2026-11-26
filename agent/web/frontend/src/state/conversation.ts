import type { AgentEvent, ContextUsage, HistoryPage, ImageAsset, Model, SessionState, ToolProcess, QuestionOption, QuestionAnswer } from '../api/types';

export type TextItem = { id: string; kind: 'text'; role: 'user' | 'assistant'; content: string; images?: string[];
  guidance?: 'queued' | 'applied' | 'undelivered' };
export type ToolItem = { id: string; kind: 'tool'; name: string; callId?: string; arguments?: unknown; result?: unknown; readImageIds?: string[]; process?: ToolProcess; status: 'running' | 'completed' | 'interrupted' | 'skipped' | 'rejected' };
export type ExecutionItem = TextItem | ToolItem;
export type ContextCompactionItem = { id: string; kind: 'context'; status: 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'; reason?: string };
export type ReportItem = { id: string; kind: 'report'; content: string; process: ExecutionItem[]; durationSeconds: number | null };
export type QuestionItem = { id: string; kind: 'question'; questionId: string; callId: string; runId?: string;
  question: string; options: QuestionOption[]; status: 'pending' | 'answered' | 'cancelled'; answer?: QuestionAnswer };
export type Item = ExecutionItem | ReportItem | ContextCompactionItem | QuestionItem;
export interface Conversation {
  contextUsage: ContextUsage | null;
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
  minSeq: number;
  hasMore: boolean;
  history: AgentEvent[];
  snapshotSeq: number;
  live: AgentEvent[];
  revision: number;
}

export const emptyConversation = (): Conversation => ({
  contextUsage: null, items: [], images: [], seq: 0, assistantId: null, busy: false, ready: false,
  model: null, error: null, session: null, execution: null,
  minSeq: 0, hasMore: false, history: [], snapshotSeq: 0, live: [], revision: 0,
});

export type Action =
  | { type: 'reset' }
  | { type: 'restore'; view: Conversation }
  | { type: 'history'; page: HistoryPage; older?: boolean }
  | { type: 'initialize'; session: SessionState }
  | { type: 'ready'; seq: number }
  | { type: 'disconnected' }
  | { type: 'events'; events: AgentEvent[] }
  | { type: 'busy'; busy: boolean }
  | { type: 'model'; model: Model }
  | { type: 'image'; image: ImageAsset }
  | { type: 'error'; error: string | null };

function eventImages(event: AgentEvent): ImageAsset[] {
  if (event.type === 'tool.completed') {
    return event.tool === 'read_image' ? event.model_images ?? [] : [];
  }
  return 'images' in event ? event.images ?? [] : [];
}

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
    case 'guidance.queued':
      next.items = [...state.items, { id: `guidance:${event.messageId}`, kind: 'text', role: 'user',
        content: event.content, images: event.images?.map(image => image.id), guidance: 'queued' }];
      break;
    case 'guidance.applied': {
      const index = state.items.findIndex(item => item.id === `guidance:${event.messageId}`);
      next.items = state.items.map(item => item.id === `guidance:${event.messageId}` && item.kind === 'text'
        ? { ...item, guidance: 'applied' } : item);
      if (index >= 0) next.execution = { startIndex: Math.max(state.execution?.startIndex ?? 0, index + 1), startedAt: event.time };
      next.assistantId = null;
      break;
    }
    case 'guidance.undelivered':
      next.items = state.items.map(item => item.id === `guidance:${event.messageId}` && item.kind === 'text'
        ? { ...item, guidance: 'undelivered' } : item);
      break;
    case 'model.started': next.assistantId = null; break;
    case 'model.interrupted':
      if (event.answer) next.items = state.assistantId
        ? state.items.map(item => item.kind === 'text' && item.id === state.assistantId ? { ...item, content: event.answer } : item)
        : appendExecution(state.items, { id: `assistant:${event.seq}`, kind: 'text', role: 'assistant', content: event.answer });
      next.assistantId = null;
      break;
    case 'context.measured':
      if (event.seq > (state.session?.seq ?? 0)) next.contextUsage = { usedTokens: event.usedTokens, limitTokens: event.limitTokens, estimated: event.estimated };
      break;
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
    case 'question.requested':
      next.assistantId = null;
      next.items = appendExecution(state.items.filter(item => item.id !== toolKey(event)), {
        id: `question:${event.questionId}`, kind: 'question', questionId: event.questionId, callId: event.callId, runId: event.runId,
        question: event.question, options: event.options, status: 'pending',
      });
      break;
    case 'question.answered':
    case 'question.cancelled':
      next.items = state.items.map(item => item.kind === 'question' && item.questionId === event.questionId
        ? { ...item, status: event.type === 'question.answered' ? 'answered' : 'cancelled',
          answer: event.type === 'question.answered' ? event.answer : undefined } : item);
      break;
    case 'tool.requested':
    case 'tool.process':
    case 'tool.completed': {
      if (event.tool === 'submit' || (event.tool === 'ask_user' && state.items.some(item =>
        item.kind === 'question' && toolKey(item) === toolKey(event)))) break;
      next.items = upsertTool(state.items, event);
      break;
    }
    case 'report.submitted': {
      const startIndex = state.execution?.startIndex ?? state.items.length;
      const startedAt = state.execution?.startedAt;
      next.items = [...state.items.slice(0, startIndex),
        ...state.items.slice(startIndex).filter(item => item.kind === 'context' || item.kind === 'question'), {
        id: `report:${event.seq}`, kind: 'report', content: event.content,
        process: state.items.slice(startIndex).filter((item): item is ExecutionItem => item.kind === 'text' || item.kind === 'tool'),
        durationSeconds: startedAt !== undefined && event.time !== undefined
          ? Math.max(0, Math.floor((event.time - startedAt) / 1e9)) : null,
      }];
      next.execution = null;
      next.assistantId = null;
      break;
    }
    case 'model.changed':
      next.model = event.new;
      if (event.seq > (state.session?.seq ?? 0)) next.contextUsage = null;
      break;
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
  for (const image of eventImages(event)) {
    if (event.seq > (state.session?.seq ?? 0) || !next.images.some(entry => entry.id === image.id)) {
      next.images = upsertImage(next.images, image);
    }
  }
  return next;
}

type ToolEvent = Extract<AgentEvent, { type: 'tool.requested' | 'tool.process' | 'tool.completed' }>;

function toolKey({ runId, callId }: { runId?: string; callId: string }): string {
  return runId ? `tool-run:${JSON.stringify([runId, callId])}` : `tool:${callId}`;
}

function upsertTool(items: Item[], event: ToolEvent): Item[] {
  const id = toolKey(event);
  const patch: Partial<ToolItem> = event.type === 'tool.requested' ? { arguments: event.arguments }
    : event.type === 'tool.process' ? { process: event.process } : {
      result: event.result,
      readImageIds: [...new Set(eventImages(event).map(image => image.id))],
      status: event.status ?? (String(event.result).startsWith('[tool cancelled]') ? 'interrupted'
        : String(event.result).startsWith('[tool denied]') ? 'rejected' : 'completed'),
    };
  let found = false;
  const update = <T extends Item>(item: T): T => {
    if (item.kind !== 'tool' || item.id !== id) return item;
    found = true;
    return { ...item, ...patch };
  };
  const updated = items.map(item => {
    if (item.kind !== 'report') return update(item);
    // Completion can arrive after a report has collected the execution steps.
    const process = item.process.map(update);
    return process.some((step, index) => step !== item.process[index]) ? { ...item, process } : item;
  });
  if (found) return updated;
  // A history page can start at a process/result event; do not invent the arguments.
  const status = event.type === 'tool.process' && event.process.reason !== 'running' ? 'completed' : 'running';
  return appendExecution(items, { id, kind: 'tool', name: event.tool, status,
    ...(event.runId ? { callId: event.callId } : {}), ...patch });
}

function appendExecution(items: Item[], item: Item): Item[] {
  const index = items.findIndex(entry => entry.kind === 'text' && entry.guidance === 'queued');
  return index < 0 ? [...items, item] : [...items.slice(0, index), item, ...items.slice(index)];
}

function interruptPending(items: Item[]): Item[] {
  // An idle runtime or a stopped turn does not mean accepted guidance was lost.
  // Only guidance.undelivered can declare it undelivered; the server may carry it into the next turn.
  return items.map(item => item.kind === 'question' && item.status === 'pending' ? { ...item, status: 'cancelled' }
    : (item.kind === 'tool' || item.kind === 'context') && item.status === 'running'
    ? { ...item, status: 'interrupted' } : item);
}

// Older pages are only rebuilt on a button click, never for each streaming delta.
// One renderer handles both initial replay and live updates.
function rebuild(state: Conversation, history: AgentEvent[], live: AgentEvent[], page: HistoryPage): Conversation {
  const session = state.session;
  const seed = { ...emptyConversation(), session, model: state.model, images: state.images,
    minSeq: page.min_seq, hasMore: page.has_more, history, snapshotSeq: state.snapshotSeq, live,
    revision: state.revision + 1 };
  const merged = [...history, ...live].sort((a, b) => a.seq - b.seq);
  const seen = new Set<number>();
  let result = merged.reduce((view, event) => {
    if (seen.has(event.seq)) return view;
    seen.add(event.seq);
    return applyEvent(view, event);
  }, seed);
  // Keep the server's current metadata; historical model/image events can be stale.
  const snapshot = session?.seq ?? page.snapshot_seq;
  // Images were merged during replay; only the selected model needs snapshot precedence.
  const later = live.filter(event => event.seq > snapshot);
  const changedModel = later.filter(event => event.type === 'model.changed').at(-1);
  result = { ...result,
    model: changedModel?.type === 'model.changed' ? changedModel.new : state.model,
    contextUsage: state.contextUsage,
    busy: state.busy,
    ready: state.ready, error: state.error };
  if (state.ready && !state.busy) {
    result.items = interruptPending(result.items);
  }
  return result;
}

export function conversationReducer(state: Conversation, action: Action): Conversation {
  switch (action.type) {
    case 'reset': return emptyConversation();
    case 'restore': return { ...action.view, ready: false, session: null, error: null };
    case 'history': {
      const { page } = action;
      if (page.events.some((event, index) => event.seq !== page.min_seq + index) ||
          (page.events.length > 0 && page.events.at(-1)!.seq > page.snapshot_seq)) return state;
      if (!action.older) {
        const seed = { ...emptyConversation(), minSeq: page.min_seq, hasMore: page.has_more,
          history: page.events, snapshotSeq: page.snapshot_seq, revision: state.revision + 1, seq: page.min_seq ? page.min_seq - 1 : 0 };
        return page.events.reduce(applyEvent, seed);
      }
      if (!state.minSeq || !state.hasMore || page.snapshot_seq !== state.snapshotSeq ||
          page.events.at(-1)?.seq !== state.minSeq - 1) return state;
      const history = [...page.events, ...state.history];
      return rebuild(state, history, state.live, page);
    }
    case 'initialize': return { ...(action.session.reset ? emptyConversation() : state),
      session: action.session, contextUsage: action.session.contextUsage ?? null, ready: false, model: action.session.model,
      images: action.session.images ?? [], busy: action.session.busy };
    case 'ready': {
      if (!state.session || action.seq !== state.session.seq || state.seq < action.seq) return state;
      const busy = state.seq === action.seq ? state.session.busy : state.busy;
      return { ...state, ready: true, busy,
        model: state.seq === action.seq ? state.session.model : state.model,
        items: busy ? state.items : interruptPending(state.items) };
    }
    case 'disconnected': return { ...state, ready: false };
    case 'events': {
      const incoming = action.events.filter(event => event.seq > state.seq);
      const next = incoming.reduce(applyEvent, state);
      return incoming.length ? { ...next, live: [...state.live, ...incoming] } : next;
    }
    case 'busy': return { ...state, busy: action.busy };
    case 'model': return { ...state, model: action.model, contextUsage: null };
    case 'image': return { ...state, images: upsertImage(state.images, action.image) };
    case 'error': return { ...state, error: action.error };
  }
}

function upsertImage(images: ImageAsset[], image: ImageAsset): ImageAsset[] {
  return images.some(entry => entry.id === image.id)
    ? images.map(entry => entry.id === image.id ? image : entry)
    : [...images, image];
}
