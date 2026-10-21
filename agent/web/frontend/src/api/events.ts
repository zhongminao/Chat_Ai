import type { AgentEvent, SessionState } from './types';
import { api } from './client';

export function subscribe(
  id: string,
  handlers: { initialize: (state: SessionState) => void; ready: (seq: number) => void;
    events: (events: AgentEvent[]) => void; connection: (connected: boolean) => void; error: (message: string) => void },
  after = 0,
): () => void {
  const source = new EventSource(api.eventsUrl(id, after));
  let pending: AgentEvent[] = [];
  let acknowledged = after;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const fatal = (error: string) => {
    stopped = true; source.close();
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined; pending = [];
    handlers.connection(false); handlers.error(error);
  };
  const flush = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    if (pending.length) {
      handlers.events(pending);
      acknowledged = pending.at(-1)!.seq;
      pending = [];
    }
  };
  source.onopen = () => { if (!stopped) handlers.connection(true); };
  source.onerror = () => {
    if (stopped) return;
    flush(); handlers.connection(false);
    if (source.readyState === EventSource.CLOSED) fatal('会话连接已关闭，请重新打开会话');
  };
  source.onmessage = message => {
    if (stopped) return;
    try {
      const event = JSON.parse(message.data);
      if (!Number.isSafeInteger(event.seq) || event.seq < 0 || typeof event.type !== 'string') {
        fatal('收到无法识别的执行事件');
        return;
      }
      if (event.type === 'session.init') {
        flush();
        if (event.id !== id || !Number.isSafeInteger(event.after) || event.after < 0 || event.after > event.seq ||
            typeof event.reset !== 'boolean' || typeof event.busy !== 'boolean' || !event.model) {
          fatal('收到无法识别的会话初始化状态'); return;
        }
        if (event.reset && event.seq < acknowledged) {
          // A journal replacement requires a new HTTP snapshot. Never replay
          // from 1 into a partial display history.
          fatal('会话历史已变化，请重新打开会话'); return;
        }
        if (event.after > acknowledged) {
          fatal('会话续传游标跳跃，请重新打开会话'); return;
        }
        handlers.initialize(event as SessionState); return;
      }
      if (event.type === 'session.ready') { flush(); handlers.ready(event.seq); return; }
      if (event.seq <= acknowledged || pending.some(item => item.seq === event.seq)) return;
      const expected = pending.at(-1)?.seq ?? acknowledged;
      if (event.seq !== expected + 1) {
        fatal('会话事件不连续，请重新打开会话'); return;
      }
      pending.push(event as AgentEvent);
      timer ??= setTimeout(flush, 32);
    } catch { if (!stopped) fatal('执行事件解析失败'); }
  };
  return () => {
    stopped = true; source.close();
    if (timer !== undefined) clearTimeout(timer);
    pending = [];
  };
}
