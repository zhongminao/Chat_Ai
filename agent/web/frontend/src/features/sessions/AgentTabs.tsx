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
  const children = sessions.filter(item => item.parent_session_id === mainId)
    .sort((a, b) => (a.createdAt ?? '').localeCompare(b.createdAt ?? ''));
  const labels: Record<string, string> = { running: '执行中', submitted: '已提交', failed: '失败', cancelled: '已停止' };
  const label = (child: SessionSummary, index: number) =>
    `子 agent ${index + 1}${labels[child.status ?? ''] ? ` · ${labels[child.status!]}` : ''}`;
  useLayoutEffect(() => {
    const tabs = childTabs.current;
    if (!tabs) { setCollapsed(false); return; }
    const measure = () => setCollapsed(tabs.scrollWidth > tabs.clientWidth);
    const observer = new ResizeObserver(measure);
    observer.observe(tabs);
    measure();
    return () => observer.disconnect();
  }, [mainId, children.length, children.map(child => child.status).join(',')]);
  return <nav className="agent-tabs" aria-label="主子 agent 导航">
    {main && <button className={selected === main.id ? 'active' : ''} aria-current={selected === main.id ? 'page' : undefined}
      title={main.title} onClick={() => onSelect(main.id)}>主 agent</button>}
    {children.length > 0 && <div className={`agent-children${collapsed ? ' collapsed' : ''}`}>
      <div className="agent-child-tabs" ref={childTabs} aria-hidden={collapsed} inert={collapsed}>
        {children.map((child, index) => <button key={child.id} className={selected === child.id ? 'active' : ''}
          aria-current={selected === child.id ? 'page' : undefined} title={child.title} onClick={() => onSelect(child.id)}>
          {label(child, index)}
        </button>)}
      </div>
      {collapsed && <select className={`agent-child-picker${selected !== mainId ? ' active' : ''}`}
        aria-label="选择子 agent" value={selected === mainId ? '' : selected ?? ''}
        onChange={event => onSelect(event.target.value)}>
        <option value="" disabled>子 agent（{children.length}）</option>
        {children.map((child, index) => <option key={child.id} value={child.id}>{label(child, index)} — {child.title}</option>)}
      </select>}
    </div>}
    {status}
  </nav>;
}
