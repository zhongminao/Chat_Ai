export interface SessionSummary {
  id: string;
  title: string;
  createdAt: string | null;
  updatedAt: number;
  empty?: boolean;
  parent_session_id?: string | null;
  busy?: boolean;
  status?: 'idle' | 'running' | 'submitted' | 'failed' | 'cancelled';
}

export interface Model {
  provider: string;
  name: string;
  thinking?: string;
}

export interface ModelGroup {
  provider: string;
  displayName: string;
  models: { id: string; name: string; enabled: boolean }[];
}

export interface Snapshot {
  id: string;
  seq: number;
  busy: boolean;
  model: Model;
  parent_session_id?: string | null;
  messages?: unknown[];
  images?: ImageAsset[];
}

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

interface EventEnvelope { seq: number; runId?: string; time?: number }
export type AgentEvent = EventEnvelope & (
  | { type: 'turn.started'; prompt: string; source?: 'agent_report'; images?: ImageAsset[] }
  | { type: 'image.renamed'; image: ImageAsset }
  | { type: 'model.started'; round: number }
  | { type: 'message.delta'; text: string; round: number }
  | { type: 'tool.requested'; callId: string; tool: string; arguments: unknown }
  | { type: 'tool.completed'; callId: string; tool: string; result: unknown; images?: ImageAsset[] }
  | { type: 'model.changed'; new: Model }
  | { type: 'agent.created'; session_id: string }
  | { type: 'report.submitted'; content: string }
  | { type: 'report.received'; session_id: string; content: string; status: 'submitted' | 'failed' | 'cancelled' }
  | { type: 'turn.completed'; answer?: string }
  | { type: 'turn.cancelled'; answer?: string }
  | { type: 'turn.failed'; reason: string }
  | { type: 'error'; message: string; reason?: string }
  | { type: 'model.completed' | 'reasoning.delta' | 'tool_call.delta' }
);
