import { useRef, useState } from 'react';
import type { SessionSummary } from '../../api/types';
import { Icon } from '../../ui/Icon';
import { SessionMenu } from './SessionMenu';
import './sessions.css';

interface Props {
  session: SessionSummary;
  selected: boolean;
  busy: boolean;
  deleting: string | null;
  renaming: string | null;
  updating: string | null;
  onUpdate: (id: string, changes: { pinned?: boolean; archived?: boolean }) => Promise<boolean>;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => Promise<boolean>;
}

export function SessionRow({ session, ...props }: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session.title);
  const [failed, setFailed] = useState(false);
  const saving = useRef(false);
  const disabled = Boolean(props.deleting || props.renaming || props.updating);

  async function save() {
    if (disabled || saving.current) return;
    const value = title.trim();
    if (!value || value === session.title) { setEditing(false); return; }
    saving.current = true; setFailed(false);
    try {
      if (await props.onRename(session.id, value)) setEditing(false);
      else setFailed(true);
    } finally { saving.current = false; }
  }

  return <div className={`session-row ${props.selected ? 'active' : ''}`}>
    {editing ? <form className="session-rename" aria-busy={props.renaming === session.id}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) void save();
      }}
      onSubmit={event => { event.preventDefault(); void save(); }}>
      <input autoFocus maxLength={80} value={title} disabled={disabled} aria-label="会话名称"
        onFocus={event => event.currentTarget.select()} onChange={event => { setTitle(event.target.value); setFailed(false); }}
        onKeyDown={event => {
          if (event.key === 'Enter' && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault();
          if (event.key === 'Escape' && !event.nativeEvent.isComposing) {
            event.preventDefault(); if (!disabled) setEditing(false);
          }
        }} />
      <div className="session-rename-actions">
        <button type="submit" className="icon-button" disabled={disabled} aria-label="保存会话名称" title="保存（Enter / 点击外部）">
          <Icon name="check" size={14} />
        </button>
        <button type="button" className="icon-button" disabled={disabled} aria-label="取消改名" title="取消（Esc）"
          onClick={() => setEditing(false)}><Icon name="close" size={14} /></button>
      </div>
      {failed && <span className="session-rename-error" role="alert">未保存，请检查名称或连接后重试</span>}
    </form> : <>
      <button className="session-select" aria-current={props.selected ? 'page' : undefined}
        onClick={() => props.onSelect(session.id)} title={session.title}>
        <span className="session-title">{session.title}</span>
      </button>
      <SessionMenu title={session.title} pinned={Boolean(session.pinned)} archived={Boolean(session.archived)}
        disabled={disabled} deleteDisabled={props.selected && props.busy}
        onRename={() => { setTitle(session.title); setFailed(false); setEditing(true); }}
        onPin={() => { void props.onUpdate(session.id, { pinned: !session.pinned }); }}
        onArchive={() => { void props.onUpdate(session.id, { archived: !session.archived }); }}
        onDelete={() => props.onDelete(session.id)} />
    </>}
  </div>;
}
