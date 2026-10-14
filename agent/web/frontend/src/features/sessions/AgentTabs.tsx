import type { SessionSummary } from '../../api/types';

export function AgentTabs({ sessions, selected, onSelect }: {
  sessions: SessionSummary[]; selected: string | null; onSelect: (id: string) => void;
}) {
  const current = sessions.find(item => item.id === selected);
  const mainId = current?.parent_session_id ?? selected;
  const main = sessions.find(item => item.id === mainId);
  const children = sessions.filter(item => item.parent_session_id === mainId)
    .sort((a, b) => (a.createdAt ?? '').localeCompare(b.createdAt ?? ''));
  const labels: Record<string, string> = { running: '执行中', submitted: '已提交', failed: '失败', cancelled: '已停止' };
  return <nav className="agent-tabs" aria-label="主子 agent 导航">
    {main && <button className={selected === main.id ? 'active' : ''} aria-current={selected === main.id ? 'page' : undefined}
      title={main.title} onClick={() => onSelect(main.id)}>主 agent</button>}
    {children.map((child, index) => <button key={child.id} className={selected === child.id ? 'active' : ''}
      aria-current={selected === child.id ? 'page' : undefined} title={child.title} onClick={() => onSelect(child.id)}>
      子 agent {index + 1}{labels[child.status ?? ''] && <span> · {labels[child.status!]}</span>}
    </button>)}
  </nav>;
}
