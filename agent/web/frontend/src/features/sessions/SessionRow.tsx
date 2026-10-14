import { useState } from 'react';
import type { SessionSummary } from '../../api/types';
import { Icon } from '../../ui/Icon';
import './sessions.css';

const date = (seconds: number) => new Date(seconds * 1000).toLocaleString('zh-CN', {
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
});

interface Props {
  session: SessionSummary;
  selected: boolean;
  busy: boolean;
  deleting: string | null;
  renaming: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => Promise<boolean>;
}

export function SessionRow({ session, ...props }: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session.title);
  const [failed, setFailed] = useState(false);
  const disabled = Boolean(props.deleting || props.renaming);

  async function save() {
    if (disabled) return;
    setFailed(false);
    if (await props.onRename(session.id, title)) setEditing(false);
    else setFailed(true);
  }

  return <div className={`session-row ${props.selected ? 'active' : ''}`}>
    {editing ? <form className="session-rename" aria-busy={props.renaming === session.id}
      onSubmit={event => { event.preventDefault(); void save(); }}>
      <input autoFocus required maxLength={80} value={title} disabled={disabled} aria-label="会话名称"
        onFocus={event => event.currentTarget.select()} onChange={event => { setTitle(event.target.value); setFailed(false); }}
        onKeyDown={event => {
          if (event.key === 'Enter' && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault();
          if (event.key === 'Escape' && !event.nativeEvent.isComposing) {
            event.preventDefault(); if (!disabled) setEditing(false);
          }
        }} />
      <div className="session-rename-actions">
        <button type="submit" className="icon-button" disabled={disabled} aria-label="保存会话名称" title="保存（Enter）">
          <Icon name="check" size={14} />
        </button>
        <button type="button" className="icon-button" disabled={disabled} aria-label="取消改名" title="取消（Esc）"
          onClick={() => setEditing(false)}><Icon name="close" size={14} /></button>
      </div>
      {failed && <span className="session-rename-error" role="alert">未保存，请检查名称或连接后重试</span>}
    </form> : <>
      <button className="session-select" aria-current={props.selected ? 'page' : undefined}
        onClick={() => props.onSelect(session.id)} title={session.title}>
        <span className="session-title">{session.title}</span><time>{date(session.updatedAt)}</time>
      </button>
      <button className="session-action icon-button" aria-label={`修改会话名称：${session.title}`} title="修改会话名称"
        disabled={disabled} onClick={() => { setTitle(session.title); setFailed(false); setEditing(true); }}><Icon name="edit" size={14} /></button>
      <button className="session-action session-delete icon-button" aria-label={`删除会话：${session.title}`} title="删除会话"
        disabled={disabled || (props.selected && props.busy)} onClick={() => props.onDelete(session.id)}>
        <Icon name="close" size={14} />
      </button>
    </>}
  </div>;
}
