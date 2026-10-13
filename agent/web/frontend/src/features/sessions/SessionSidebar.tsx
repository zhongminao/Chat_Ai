import type { SessionSummary } from '../../api/types';
import { Icon } from '../../ui/Icon';

const date = (seconds: number) => new Date(seconds * 1000).toLocaleString('zh-CN', {
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
});

interface Props {
  sessions: SessionSummary[];
  selected: string | null;
  loading: boolean;
  creating: boolean;
  deleting: string | null;
  open: boolean;
  busy: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

export function SessionSidebar(props: Props) {
  return <>
    {props.open && <button className="sidebar-backdrop" aria-label="关闭会话列表" onClick={props.onClose} />}
    <aside className={`sidebar ${props.open ? 'is-open' : ''}`} aria-label="会话列表">
      <div className="sidebar-heading"><span className="brand">chat_ai</span>
        <button className="icon-button mobile-only" aria-label="关闭会话列表" onClick={props.onClose}><Icon name="close" /></button>
      </div>
      <button className="new-session" onClick={props.onCreate} disabled={props.loading || props.creating}>
        <Icon name="plus" />{props.creating ? '正在创建…' : '新会话'}
      </button>
      <div className="sidebar-label">历史会话</div>
      <nav className="session-list" aria-label="历史会话">
        {props.loading && <p className="muted sidebar-empty">加载中…</p>}
        {!props.loading && !props.sessions.length && <p className="muted sidebar-empty">暂无历史会话</p>}
        {props.sessions.map(session => <div className={`session-row ${session.id === props.selected ? 'active' : ''}`} key={session.id}>
          <button className="session-select" aria-current={session.id === props.selected ? 'page' : undefined}
            onClick={() => props.onSelect(session.id)} title={session.title}>
            <span className="session-title">{session.title}</span><time>{date(session.updatedAt)}</time>
          </button>
          <button className="session-delete icon-button" aria-label={`删除会话：${session.title}`} title="删除会话"
            disabled={Boolean(props.deleting) || (session.id === props.selected && props.busy)} onClick={() => props.onDelete(session.id)}>
            <Icon name="close" size={14} />
          </button>
        </div>)}
      </nav>
      <div className="sidebar-footer"><span className="brand-mark" aria-hidden="true">a</span><span>Agent workspace</span></div>
    </aside>
  </>;
}
