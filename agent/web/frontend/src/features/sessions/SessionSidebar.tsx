import { useState } from 'react';
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
  updating: string | null;
  onUpdate: (id: string, changes: { pinned?: boolean; archived?: boolean }) => Promise<boolean>;
  onRename: (id: string, title: string) => Promise<boolean>;
  open: boolean;
  busy: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}

export function SessionSidebar(props: Props) {
  const [archiveOpen, setArchiveOpen] = useState(false);
  const roots = props.sessions.filter(session => !session.parent_session_id);
  const active = roots.filter(session => !session.archived).sort((a, b) => b.updatedAt - a.updatedAt);
  const pinned = active.filter(session => session.pinned);
  const history = active.filter(session => !session.pinned);
  const archived = roots.filter(session => session.archived).sort((a, b) => b.updatedAt - a.updatedAt);
  const selectedRoot = props.sessions.find(session => session.id === props.selected)?.parent_session_id ?? props.selected;
  const row = (session: SessionSummary) => <SessionRow key={session.id} session={session}
    selected={session.id === selectedRoot} busy={props.busy} deleting={props.deleting} renaming={props.renaming}
    updating={props.updating} onUpdate={props.onUpdate}
    onSelect={props.onSelect} onDelete={props.onDelete} onRename={props.onRename} />;

  return <>
    {props.open && <button className="sidebar-backdrop" aria-label="关闭会话列表" onClick={props.onClose} />}
    <aside className={`sidebar ${props.open ? 'is-open' : ''}`} aria-label="会话列表">
      <div className="sidebar-heading"><span className="brand">chat_ai</span>
        <button className="icon-button mobile-only" aria-label="关闭会话列表" onClick={props.onClose}><Icon name="close" /></button>
      </div>
      <button className="new-session" onClick={props.onCreate} disabled={props.loading || props.creating}>
        <Icon name="plus" />{props.creating ? '正在创建…' : '新会话'}
      </button>
      <div className="session-list session-groups">
        {props.loading && <p className="muted sidebar-empty">加载中…</p>}
        {pinned.length > 0 && <section className="session-group" aria-label="置顶会话">
          <div className="sidebar-label">置顶会话</div>
          <nav aria-label="置顶会话列表">{pinned.map(row)}</nav>
        </section>}
        <section className="session-group" aria-label="历史会话">
          <div className="sidebar-label">历史会话</div>
          <nav aria-label="历史会话列表">
            {!props.loading && !history.length && <p className="muted sidebar-empty">暂无历史会话</p>}
            {history.map(row)}
          </nav>
        </section>
      </div>
      <section className={`session-archive ${archiveOpen ? 'is-open' : ''}`} aria-label="归档会话">
        <button className="archive-toggle" aria-expanded={archiveOpen} aria-controls="archived-sessions"
          onClick={() => setArchiveOpen(value => !value)}>
          <Icon name="archive" size={17} /><span>归档会话</span><span className="archive-count">{archived.length}</span>
          <Icon name="down" size={14} />
        </button>
        {archiveOpen && <nav id="archived-sessions" className="session-list archive-list" aria-label="归档会话列表">
          {!archived.length && <p className="muted sidebar-empty">暂无归档会话</p>}
          {archived.map(row)}
        </nav>}
      </section>
    </aside>
  </>;
}
