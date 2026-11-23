export interface SessionSummary {
  id: string;
  title: string;
  createdAt: string | null;
  updatedAt: number;
  activitySeq?: number;
  empty?: boolean;
  pinned?: boolean;
  archived?: boolean;
  archivedAt?: number | null;
  parent_session_id?: string | null;
  busy?: boolean;
  status?: 'idle' | 'running' | 'submitted' | 'failed' | 'cancelled';
}

export interface WatchResource {
  id: string; kind?: string; session_id?: string; title?: string;
  status?: string; result_path?: string; error?: string; version: number; deleted?: boolean;
}

export interface WatchResult { cursor: number; changes: WatchResource[] }

export interface Model {
  provider: string;
  name: string;
  thinking?: string;
  reasoning_effort?: string;
}

export interface ModelGroup {
  provider: string;
  displayName: string;
  models: { id: string; name: string; enabled: boolean; reasoning_efforts?: string[];
    default_reasoning_effort?: string; api_default_reasoning_effort?: string }[];
}

export interface HistoryPage {
  events: AgentEvent[];
  snapshot_seq: number;
  min_seq: number;
  has_more: boolean;
}

export interface ContextUsage { usedTokens: number; limitTokens: number; estimated: boolean }

export interface SessionState {
  contextUsage?: ContextUsage | null;
  id: string;
  seq: number;
  after: number;
  reset: boolean;
  busy: boolean;
  model: Model;
  parent_session_id?: string | null;
  images?: ImageAsset[];
}

export type AccessMode = 'audit' | 'full_access';
export interface ApprovalRequest {
  id: string; sessionId: string; runId: string; callId: string;
  tool: string; arguments: Record<string, unknown>;
  workspace?: string | null;
}
export interface ApprovalSnapshot { mode: AccessMode; instanceId: string; revision: number; pending: ApprovalRequest[] }

export interface FileAsset { id: string; name: string; filename: string; path: string; size: number; kind?: 'file' | 'folder' }

export interface ImageAsset {
  id: string;
  name: string;
  ordinal: number;
  filename: string;
  mime: string;
  width: number;
  height: number;
  size: number;
}

export interface ToolProcess {
  pid: number;
  pgid: number;
  exitCode: number | null;
  reason: 'running' | 'exited' | 'timeout' | 'cancelled' | 'error';
}

export interface QuestionOption { title: string; description: string }
export interface QuestionAnswer { option_index: number | null; text: string }

interface EventEnvelope { seq: number; runId?: string; time?: number }
export type AgentEvent = EventEnvelope & (
  | { type: 'turn.started'; prompt: string; images?: ImageAsset[]; currentTime?: string }
  | { type: 'guidance.queued' | 'guidance.applied'; messageId: string; content: string; images?: ImageAsset[] }
  | { type: 'guidance.undelivered'; messageId: string }
  | { type: 'mailbox.notified'; messageIds: string[] }
  | { type: 'model.started'; round: number }
  | { type: 'message.delta'; text: string; round: number }
  | { type: 'tool.requested'; callId: string; tool: string; arguments: unknown }
  | { type: 'question.requested'; questionId: string; callId: string; question: string; options: QuestionOption[] }
  | { type: 'question.answered'; questionId: string; callId: string; answer: QuestionAnswer }
  | { type: 'question.cancelled'; questionId: string; callId: string }
  | { type: 'tool.process'; callId: string; tool: 'bash'; process: ToolProcess }
  | { type: 'tool.completed'; callId: string; tool: string; result: unknown; model_images?: ImageAsset[] }
  | { type: 'model.changed'; new: Model }
  | { type: 'agent.created'; session_id: string }
  | { type: 'report.submitted'; content: string }
  | { type: 'completion.reminded'; content: string }
  | ({ type: 'context.measured' } & ContextUsage)
  | { type: 'context.compaction.started'; compactionId: string; beforeTokens: number }
  | { type: 'context.compacted'; compactionId: string; beforeTokens: number; afterTokens: number }
  | { type: 'context.compaction.failed'; compactionId: string; reason: string }
  | { type: 'context.compaction.cancelled'; compactionId: string }
  | { type: 'turn.completed'; answer?: string }
  | { type: 'turn.cancelled'; answer?: string }
  | { type: 'turn.failed'; reason: string }
  | { type: 'error'; message: string; reason?: string }
  | { type: 'model.completed'; round?: number }
  | { type: 'reasoning.delta'; text?: string; round?: number }
  | { type: 'tool_call.delta' }
);
