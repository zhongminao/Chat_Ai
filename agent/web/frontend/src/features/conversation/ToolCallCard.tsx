import { useEffect, useId, useRef, useState } from 'react';
import { DisclosureSummary } from './DisclosureSummary';
import type { ToolItem } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import type { ImageAsset } from '../../api/types';
import { ImageOutput } from '../images/ImageOutput';
import { processStatus, toolFailed, toolPresentation, toolStatus, type DisclosureState } from './toolPresentation';

const format = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2);

export function ToolCallCard({ item, sessionId, images = [], waiting = false, disclosures }: {
  item: ToolItem; sessionId?: string | null; images?: ImageAsset[]; waiting?: boolean;
  disclosures: DisclosureState;
}) {
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  const outputRef = useRef<HTMLPreElement>(null);
  const outputId = useId();
  const view = toolPresentation(item);
  const result = format(item.result);
  const parameters = view.command
    ? Object.fromEntries(Object.entries(item.arguments && typeof item.arguments === 'object' ? item.arguments : {}).filter(([key]) => key !== 'command'))
    : item.arguments;
  const hasParameters = parameters !== undefined && (!view.command || Object.keys(parameters as object).length > 0);
  const failed = toolFailed(item);
  const indicator = failed ? 'error' : item.status === 'running' ? 'running' : 'completed';
  useEffect(() => {
    const output = outputRef.current;
    if (!output) return;
    const measure = () => {
      // Measure the natural content even when expanded so the collapse control stays available.
      const limit = Math.min(250, window.innerHeight * 0.5);
      setOverflowing(output.scrollHeight + output.offsetHeight - output.clientHeight > limit + 1);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(output);
    window.addEventListener('resize', measure);
    measure();
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [result, expanded, view.command]);
  const output = item.result !== undefined && <>
    <pre ref={outputRef} id={outputId}
      className={`tool-result-text${view.command ? ' command-output' : ''}${overflowing && !expanded ? ' is-scrollable' : ''}${expanded ? ' is-expanded' : ''}`}>{result}</pre>
    {overflowing && <button type="button" className="tool-output-toggle" aria-controls={outputId}
      aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
      {expanded ? '收起' : '展开全部'}
    </button>}
  </>;
  return <div className="tool-output"><details className="tool-card" open={disclosures.isOpen(item.id)}>
    <DisclosureSummary onToggle={() => disclosures.toggle(item.id)} title={item.name}>
      <span className={`tool-status-dot ${indicator}`} aria-hidden="true" />
      <span className="tool-name">{view.label}</span>
      {view.target && <code className="tool-target" title={view.target}>{view.target}</code>}
      <span className={`tool-status ${failed ? 'error' : item.status}`}>
        {failed ? '出错' : waiting && item.status === 'running' ? '等待审批' : toolStatus[item.status]}
      </span><Icon name="down" size={14} />
    </DisclosureSummary>
    <div className="tool-body">
      {view.command ? <>
        <div className={`command-transcript${failed ? ' tool-result-error' : ''}`}>
          {view.target && <pre className="command-source">{view.target}</pre>}
          {output}
        </div>
        {item.process && <div className="tool-metadata" title="仅表示本次命令的 shell 进程状态，不代表后台服务是否存活。">
          <span>shell PID: {item.process.pid}</span><span>PGID: {item.process.pgid}</span>
          <span>退出码: {item.process.exitCode === null ? '未取得' : item.process.exitCode}</span>
          <span>状态: {item.process.reason === 'running' && item.status === 'interrupted'
            ? '执行中断，退出状态未知' : processStatus[item.process.reason]}</span>
        </div>}
        {hasParameters && <div className="tool-metadata">{Object.entries(parameters as Record<string, unknown>).map(([key, value]) =>
          <span key={key}>{key}: {format(value)}</span>)}</div>}
      </> : <>
        {item.arguments !== undefined && <><div className="tool-label">调用参数</div><pre>{format(item.arguments)}</pre></>}
        {item.result !== undefined && <div className={failed ? 'tool-result-error' : undefined}>
          <div className="tool-label">工具结果</div>{output}
        </div>}
      </>}
    </div>
  </details>
    {sessionId && item.images?.length ? <ImageOutput ids={item.images} assets={images} sessionId={sessionId} /> : null}
  </div>;
}
