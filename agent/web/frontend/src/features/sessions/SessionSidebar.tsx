import type { SessionSummary } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { SessionRow } from './SessionRow';

interface Props {
  sessions: SessionSummary[];
  selected: string | null;
  loading: boolean;
  creating: boolean;
  deleting: string | null;
  renaming: string | null;
  onRename: (id: string, title: string) => Promise<boolean>;
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
        {props.sessions.map(session => <SessionRow key={session.id} session={session}
          selected={session.id === props.selected} busy={props.busy} deleting={props.deleting} renaming={props.renaming}
          onSelect={props.onSelect} onDelete={props.onDelete} onRename={props.onRename} />)}
      </nav>
      <div className="sidebar-footer"><span className="brand-mark" aria-hidden="true">a</span><span>Agent workspace</span></div>
    </aside>
  </>;
}
