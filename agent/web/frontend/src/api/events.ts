import type { AgentEvent } from './types';
import { api } from './client';

export function subscribe(
  id: string,
  handlers: { events: (events: AgentEvent[]) => void; connection: (connected: boolean) => void; error: (message: string) => void },
): () => void {
  const source = new EventSource(api.eventsUrl(id));
  let pending: AgentEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  const flush = () => {
    timer = undefined;
    if (pending.length) { handlers.events(pending); pending = []; }
  };
  source.onopen = () => handlers.connection(true);
  source.onerror = () => handlers.connection(false);
  source.onmessage = message => {
    try {
      const event = JSON.parse(message.data);
      if (event.type === 'connected') return;
      if (!Number.isInteger(event.seq) || typeof event.type !== 'string') {
        handlers.error('收到无法识别的执行事件');
        return;
      }
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
