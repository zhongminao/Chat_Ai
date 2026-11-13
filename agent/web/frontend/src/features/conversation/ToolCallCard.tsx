import { DisclosureSummary } from './DisclosureSummary';
import type { ToolItem } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import type { ImageAsset } from '../../api/types';
import { ImageOutput } from '../images/ImageOutput';
import { toolPresentation, toolStatus, type DisclosureState } from './toolPresentation';

const format = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2);

export function ToolCallCard({ item, sessionId, images = [], waiting = false, disclosures }: {
  item: ToolItem; sessionId?: string | null; images?: ImageAsset[]; waiting?: boolean;
  disclosures: DisclosureState;
}) {
  const view = toolPresentation(item);
  const result = format(item.result);
  const parameters = view.command
    ? Object.fromEntries(Object.entries(item.arguments && typeof item.arguments === 'object' ? item.arguments : {}).filter(([key]) => key !== 'command'))
    : item.arguments;
  const hasParameters = parameters !== undefined && (!view.command || Object.keys(parameters as object).length > 0);
  const failed = item.status === 'interrupted' || item.status === 'rejected'
    || (typeof result === 'string' && /^\[(?:tool|mcp) error\]/.test(result));
  const indicator = item.status === 'running' ? 'running' : failed ? 'error' : 'completed';
  return <div className="tool-output"><details className="tool-card" open={disclosures.isOpen(item.id)}>
    <DisclosureSummary onToggle={() => disclosures.toggle(item.id)} title={item.name}>
      <span className={`tool-status-dot ${indicator}`} aria-hidden="true" />
      <span className="tool-name">{view.label}</span>
      {view.target && <code className="tool-target" title={view.target}>{view.target}</code>}
      <span className={`tool-status ${failed ? 'error' : item.status}`}>
        {waiting && item.status === 'running' ? '等待审批' : failed && item.status === 'completed' ? '出错' : toolStatus[item.status]}
      </span><Icon name="down" size={14} />
    </DisclosureSummary>
    <div className="tool-body">
      {view.command ? <>
        <div className={`command-transcript${failed ? ' tool-result-error' : ''}`}>
          {view.target && <pre className="command-source">{view.target}</pre>}
          {item.result !== undefined && <pre className="command-output">{result}</pre>}
        </div>
        {hasParameters && <div className="tool-metadata">{Object.entries(parameters as Record<string, unknown>).map(([key, value]) =>
          <span key={key}>{key}: {format(value)}</span>)}</div>}
      </> : <>
        {item.arguments !== undefined && <><div className="tool-label">调用参数</div><pre>{format(item.arguments)}</pre></>}
        {item.result !== undefined && <div className={failed ? 'tool-result-error' : undefined}>
          <div className="tool-label">工具结果</div><pre>{result}</pre>
        </div>}
      </>}
    </div>
  </details>
    {sessionId && item.images?.length ? <ImageOutput ids={item.images} assets={images} sessionId={sessionId} /> : null}
  </div>;
}
