import { DisclosureSummary } from './DisclosureSummary';
import type { ImageAsset } from '../../api/types';
import type { ToolItem } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import { ToolCallCard } from './ToolCallCard';
import { toolFailed, toolPresentation, toolStatus, type DisclosureState } from './toolPresentation';

function callId(item: ToolItem): string {
  return item.id.startsWith('tool:') ? item.id.slice('tool:'.length) : item.id;
}

export function ExecutionSteps({ items, sessionId, images = [], waitingCallIds = [], disclosures }: {
  items: ToolItem[];
  sessionId?: string | null;
  images?: ImageAsset[];
  waitingCallIds?: string[];
  disclosures: DisclosureState;
}) {
  if (!items.length) return null;
  const waiting = (item: ToolItem) => item.status === 'running' && waitingCallIds.includes(callId(item));
  const latest = [...items].reverse().find(item => item.status === 'running') ?? items[items.length - 1];
  const failed = toolFailed(latest);
  const latestStatus = failed ? '出错' : waiting(latest) ? '等待审批' : toolStatus[latest.status];
  const id = `steps:${items[0].id}`;
  return <details className="execution-steps" open={disclosures.isOpen(id)}>
    <DisclosureSummary onToggle={() => disclosures.toggle(id)}>
      <Icon name="tool" size={15} />
      <span>执行步骤 · {items.length} 个工具</span>
      <span className={`execution-steps-status ${failed ? 'error' : latest.status}`}>{toolPresentation(latest).label} · {latestStatus}</span>
      <Icon name="down" size={13} />
    </DisclosureSummary>
    <div className="execution-step-list">
      {items.map(item => <ToolCallCard key={item.id} item={item} disclosures={disclosures}
        sessionId={sessionId} images={images} waiting={waiting(item)} />)}
    </div>
  </details>;
}
