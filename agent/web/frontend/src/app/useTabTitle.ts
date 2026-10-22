import { useEffect } from 'react';
import type { AgentEvent } from '../api/types';

export interface TabTitleState {
  selected: string | null;
  title?: string;
  loading: boolean;
  connected: boolean;
  ready: boolean;
  busy: boolean;
  sending: boolean;
  waitingApproval: boolean;
  error: string | null;
  history: AgentEvent[];
  live: AgentEvent[];
}

export function getTabTitle(state: TabTitleState): string {
  let status: string;
  if (state.loading) status = '⏳ 正在加载';
  else if (!state.selected) status = state.error ? '❌ 出错' : '○ 未选择会话';
  else if (!state.connected) status = state.error ? '❌ 出错' : '⚠ 连接中 / 已断开';
  else if (!state.ready) status = state.error ? '❌ 出错' : '⏳ 正在恢复';
  else if (state.waitingApproval) status = '🔔 等待审批';
  else if (state.busy || state.sending) status = '⏳ 执行中';
  else if (state.error) status = '❌ 出错';
  else {
    // Use persisted events as well as live events, so refresh/reconnect retains
    // the outcome. Ignore later metadata events (e.g. model/image changes).
    let latest: AgentEvent | undefined;
    for (const events of [state.history, state.live]) {
      for (let i = events.length - 1; i >= 0; i--) {
        const event = events[i];
        if (['turn.started', 'turn.completed', 'turn.failed', 'turn.cancelled'].includes(event.type)) {
          if (!latest || event.seq > latest.seq) latest = event;
          break;
        }
      }
    }
    status = latest?.type === 'turn.completed' ? '✅ 已完成'
      : latest?.type === 'turn.failed' ? '❌ 失败'
      : latest?.type === 'turn.cancelled' ? '⏹ 已停止' : '○ 就绪';
  }
  const title = state.selected ? state.title?.trim() : '';
  return `${status}${title ? ` · ${title}` : ''}`;
}

export function useTabTitle(state: TabTitleState) {
  const title = getTabTitle(state);
  useEffect(() => { document.title = title; }, [title]);
}
