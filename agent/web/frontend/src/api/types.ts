export interface SessionSummary {
  id: string;
  title: string;
  createdAt: string | null;
  updatedAt: number;
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
  messages?: unknown[];
}

interface EventEnvelope { seq: number; runId?: string; time?: number }
export type AgentEvent = EventEnvelope & (
  | { type: 'turn.started'; prompt: string }
  | { type: 'model.started'; round: number }
  | { type: 'message.delta'; text: string; round: number }
  | { type: 'tool.requested'; callId: string; tool: string; arguments: unknown }
  | { type: 'tool.completed'; callId: string; tool: string; result: unknown }
  | { type: 'model.changed'; new: Model }
  | { type: 'turn.completed'; answer?: string }
  | { type: 'turn.cancelled'; answer?: string }
  | { type: 'turn.failed'; reason: string }
  | { type: 'error'; message: string; reason?: string }
  | { type: 'model.completed' | 'reasoning.delta' | 'tool_call.delta' | 'agent.started' | 'agent.completed' }
);
