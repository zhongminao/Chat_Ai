import { DisclosureSummary } from './DisclosureSummary';
import { useState, type ReactNode } from 'react';
import type { ReportItem } from '../../state/conversation';
import { Icon } from '../../ui/Icon';
import { MessageContent } from './MessageContent';
import type { DisclosureState } from './toolPresentation';

export function ReportCard({ item, children, disclosures }: { item: ReportItem; children: ReactNode; disclosures: DisclosureState }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const duration = item.durationSeconds === null ? '用时未知'
    : `用时 ${Math.floor(item.durationSeconds / 60)} 分 ${item.durationSeconds % 60} 秒`;
  const [initialOpen] = useState(() => item.process.some(step => disclosures.isOpen(step.id) || disclosures.isOpen(`steps:${step.id}`)));
  return <section className="submission" aria-label="已提交的回复">
    <details className="execution-details" open={disclosures.isOpen(item.id, initialOpen)}>
      <DisclosureSummary onToggle={() => disclosures.toggle(item.id, initialOpen)}><span>{duration}</span><Icon name="down" size={14} /></DisclosureSummary>
      <div className="execution-process">{children}</div>
    </details>
    <article className="message assistant" aria-label="最终报告">
      <MessageContent content={item.content} role="assistant" streaming={false} />
      <button className="report-copy" onClick={async () => {
        try { await navigator.clipboard.writeText(item.content); setCopied(true); setCopyError(false); }
        catch { setCopyError(true); }
      }}>{copyError ? '复制失败' : copied ? '已复制' : '复制'}</button>
    </article>
  </section>;
}
