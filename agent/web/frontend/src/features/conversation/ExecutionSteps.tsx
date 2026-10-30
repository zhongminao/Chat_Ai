import type { ImageAsset } from '../../api/types';
import type { ToolItem } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import { ToolCallCard } from './ToolCallCard';

const labels = { running: '执行中', completed: '已完成', interrupted: '已中断', rejected: '已拒绝' };

function callId(item: ToolItem): string {
  return item.id.startsWith('tool:') ? item.id.slice('tool:'.length) : item.id;
}

export function ExecutionSteps({ items, sessionId, images = [], waitingCallIds = [], onInspect }: {
  items: ToolItem[];
  sessionId?: string | null;
  images?: ImageAsset[];
  waitingCallIds?: string[];
  onInspect?: () => void;
}) {
  if (!items.length) return null;
  const waiting = (item: ToolItem) => item.status === 'running' && waitingCallIds.includes(callId(item));
  const latest = [...items].reverse().find(item => item.status === 'running') ?? items[items.length - 1];
  const latestStatus = waiting(latest) ? '等待审批' : labels[latest.status];
  return <details className="execution-steps">
    <summary onClick={event => { if (!event.currentTarget.parentElement?.hasAttribute('open')) onInspect?.(); }}>
      <Icon name="tool" size={15} />
      <span>执行步骤 · {items.length} 个工具</span>
      <span className={`execution-steps-status ${latest.status}`}>{latest.name} · {latestStatus}</span>
      <Icon name="down" size={13} />
    </summary>
    <div className="execution-step-list">
      {items.map(item => <ToolCallCard key={item.id} item={item} onInspect={onInspect}
        sessionId={sessionId} images={images} waiting={waiting(item)} />)}
    </div>
  </details>;
}
