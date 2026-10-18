import type { AgentEvent, SessionState } from './types';
import { api } from './client';

export function subscribe(
  id: string,
  handlers: { initialize: (state: SessionState) => void; ready: (seq: number) => void;
    events: (events: AgentEvent[]) => void; connection: (connected: boolean) => void; error: (message: string) => void },
): () => void {
  const source = new EventSource(api.eventsUrl(id));
  let pending: AgentEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  const flush = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    if (pending.length) { handlers.events(pending); pending = []; }
  };
  source.onopen = () => handlers.connection(true);
  source.onerror = () => {
    flush(); handlers.connection(false);
    if (source.readyState === EventSource.CLOSED) handlers.error('会话连接已关闭，请刷新会话列表后重试');
  };
  source.onmessage = message => {
    try {
      const event = JSON.parse(message.data);
      if (!Number.isSafeInteger(event.seq) || event.seq < 0 || typeof event.type !== 'string') {
        handlers.error('收到无法识别的执行事件');
        return;
      }
      if (event.type === 'session.init') {
        flush();
        if (event.id !== id || !Number.isSafeInteger(event.after) || event.after < 0 || event.after > event.seq ||
            typeof event.reset !== 'boolean' || typeof event.busy !== 'boolean' || !event.model) {
          handlers.error('收到无法识别的会话初始化状态'); return;
        }
        handlers.initialize(event as SessionState); return;
      }
      if (event.type === 'session.ready') { flush(); handlers.ready(event.seq); return; }
      pending.push(event as AgentEvent);
      timer ??= setTimeout(flush, 32);
    } catch { handlers.error('执行事件解析失败'); }
  };
  return () => {
    source.close();
    if (timer !== undefined) clearTimeout(timer);
    pending = [];
  };
}
