import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { SessionSummary } from '../../api/types';

export function AgentTabs({ sessions, selected, onSelect, children: status }: {
  sessions: SessionSummary[]; selected: string | null; onSelect: (id: string) => void;
  children?: ReactNode;
}) {
  const childTabs = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState(false);
  const current = sessions.find(item => item.id === selected);
  const mainId = current?.parent_session_id ?? selected;
  const main = sessions.find(item => item.id === mainId);
  // Keep the original creation numbers while showing the newest tasks first.
  const children = sessions.filter(item => item.parent_session_id === mainId)
    .sort((a, b) => (a.createdAt ?? '').localeCompare(b.createdAt ?? '') || a.id.localeCompare(b.id))
    .map((child, index) => ({ child, ordinal: index + 1 })).reverse();
  const usePicker = collapsed || children.length > 8;
  const labels: Record<string, string> = { running: '执行中', submitted: '已提交', failed: '失败', cancelled: '已停止' };
  const label = (child: SessionSummary, ordinal: number) =>
    `子助手 ${ordinal}${labels[child.status ?? ''] ? ` · ${labels[child.status!]}` : ''}`;
  useLayoutEffect(() => {
    const tabs = childTabs.current;
    if (!tabs) { setCollapsed(false); return; }
    const measure = () => setCollapsed(tabs.scrollWidth > tabs.clientWidth);
    const observer = new ResizeObserver(measure);
    observer.observe(tabs);
    measure();
    return () => observer.disconnect();
  }, [mainId, children.length, children.map(({ child }) => `${child.id}:${child.status}`).join(',')]);
  return <nav className="agent-tabs" aria-label="主助手与子助手导航">
    {main && <button className={selected === main.id ? 'active' : ''} aria-current={selected === main.id ? 'page' : undefined}
      title={main.title} onClick={() => onSelect(main.id)}>主助手</button>}
    {children.length > 0 && <div className={`agent-children${usePicker ? ' collapsed' : ''}`}>
      <div className="agent-child-tabs" ref={childTabs} aria-hidden={usePicker} inert={usePicker}>
        {children.map(({ child, ordinal }) => <button key={child.id} className={selected === child.id ? 'active' : ''}
          aria-current={selected === child.id ? 'page' : undefined} title={child.title} onClick={() => onSelect(child.id)}>
          {label(child, ordinal)}
        </button>)}
      </div>
      {usePicker && <select className={`agent-child-picker${selected !== mainId ? ' active' : ''}`}
        aria-label="选择子助手" value={selected === mainId ? '' : selected ?? ''}
        onChange={event => onSelect(event.target.value)}>
        <option value="" disabled>子助手（{children.length}）</option>
        {children.map(({ child, ordinal }) => <option key={child.id} value={child.id}>{label(child, ordinal)} — {child.title}</option>)}
      </select>}
    </div>}
    {status}
  </nav>;
}
