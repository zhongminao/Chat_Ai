import { useLayoutEffect, useRef } from 'react';
import type { ReasoningItem } from '../../state/conversation';
import { DisclosureSummary } from './DisclosureSummary';
import type { DisclosureState } from './toolPresentation';
import './reasoningTrail.css';

const labels = { running: '思考中', completed: '已思考', stopped: '已停止思考' };

function TrailLine({ text, follow }: { text: string; follow: boolean }) {
  const row = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (follow && row.current) row.current.scrollTo({ left: row.current.scrollWidth });
  }, [text, follow]);
  return <div ref={row} className="reasoning-trail-line" tabIndex={0}>{text}</div>;
}

export function ReasoningTrail({ item, disclosures }: { item: ReasoningItem; disclosures: DisclosureState }) {
  if (!item.lines.length) return null;
  const running = item.status === 'running';
  // A terminal status closes even a manually reopened live card; it can then be reopened for reading.
  const disclosureId = `${item.id}:${item.status}`;
  const open = disclosures.isOpen(disclosureId, running);
  return <details className="reasoning-trail" data-state={item.status} open={open}>
    <DisclosureSummary onToggle={() => disclosures.toggle(disclosureId, running)}>
      <span className="reasoning-trail-dot" aria-hidden="true" />
      <span>{labels[item.status]}</span>
      <span className="reasoning-trail-chevron" aria-hidden="true">›</span>
    </DisclosureSummary>
    {open && <div className="reasoning-trail-lines" aria-live="off">
      {item.lines.map(line => <TrailLine key={line.index} text={line.text} follow={running} />)}
    </div>}
  </details>;
}
