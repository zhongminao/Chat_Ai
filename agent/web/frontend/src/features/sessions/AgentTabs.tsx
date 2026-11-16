import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Icon } from '../../ui/Icon';
import type { SessionSummary } from '../../api/types';

export function AgentTabs({ sessions, selected, onSelect, children: status }: {
  sessions: SessionSummary[]; selected: string | null; onSelect: (id: string) => void;
  children?: ReactNode;
}) {
  const picker = useRef<HTMLDetailsElement>(null);
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
  useEffect(() => {
    const menu = picker.current;
    if (!menu) return;
    menu.open = false;
    const close = (event: PointerEvent) => {
      if (!menu.contains(event.target as Node)) menu.open = false;
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && menu.open) {
        menu.open = false;
        menu.querySelector('summary')?.focus();
      }
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('keydown', escape);
    };
  }, [selected, mainId, usePicker]);
  const selectedChild = children.find(({ child }) => child.id === selected);
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
      {usePicker && <details ref={picker} className={`agent-child-picker${selectedChild ? ' active' : ''}`}>
        <summary aria-label="选择子助手">
          <span>{selectedChild ? label(selectedChild.child, selectedChild.ordinal) : `子助手（${children.length}）`}</span>
          <Icon name="down" size={14} />
        </summary>
        <div className="agent-child-options" role="group" aria-label="子助手列表">
          {children.map(({ child, ordinal }) => <button type="button" key={child.id}
            aria-current={selected === child.id ? 'page' : undefined}
            className={selected === child.id ? 'active' : ''} onClick={() => {
              picker.current!.open = false;
              onSelect(child.id);
              picker.current!.querySelector('summary')?.focus();
            }}><span>{label(child, ordinal)}</span><span className="agent-child-title">{child.title}</span></button>)}
        </div>
      </details>}
    </div>}
    {status}
  </nav>;
}
