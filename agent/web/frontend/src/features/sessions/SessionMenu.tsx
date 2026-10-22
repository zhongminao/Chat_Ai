import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '../../ui/Icon';

interface Props {
  title: string;
  pinned: boolean;
  archived: boolean;
  disabled: boolean;
  deleteDisabled: boolean;
  onRename: () => void;
  onPin: () => void;
  onArchive: () => void;
  onDelete: () => void;
}

export function SessionMenu(props: Props) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  function close(restoreFocus = false) {
    setPosition(null);
    if (restoreFocus) trigger.current?.focus();
  }

  useEffect(() => {
    if (!position) return;
    if (menu.current) {
      menu.current.style.left = `${Math.max(8, Math.min(position.left, window.innerWidth - menu.current.offsetWidth - 8))}px`;
      menu.current.querySelector<HTMLButtonElement>('button')?.focus();
    }
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setPosition(null);
    };
    const dismiss = () => setPosition(null);
    const scroll = (event: Event) => { if (!menu.current?.contains(event.target as Node)) dismiss(); };
    document.addEventListener('pointerdown', outside);
    window.addEventListener('resize', dismiss);
    window.addEventListener('scroll', scroll, true);
    return () => {
      document.removeEventListener('pointerdown', outside);
      window.removeEventListener('resize', dismiss);
      window.removeEventListener('scroll', scroll, true);
    };
  }, [position]);

  return <>
    <button ref={trigger} className={`session-action icon-button ${position ? 'is-open' : ''}`}
      aria-label={`会话操作：${props.title}`} title="更多操作" aria-haspopup="menu" aria-expanded={Boolean(position)}
      disabled={props.disabled} onClick={() => {
        if (position) { close(true); return; }
        const rect = trigger.current!.getBoundingClientRect();
        setPosition({ top: Math.max(8, Math.min(rect.top, window.innerHeight - 180)),
          left: rect.right + 8 });
      }}><Icon name="more" size={22} /></button>
    {position && createPortal(<div ref={menu} className="session-menu" role="menu" aria-label="会话操作" style={position}
      onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null) && event.relatedTarget !== trigger.current) close(); }}
      onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
          const index = items.indexOf(document.activeElement as HTMLButtonElement);
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
            : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
          items[next]?.focus();
        }
      }}>
      <button role="menuitem" disabled={props.disabled} onClick={() => { close(); props.onRename(); }}><Icon name="edit" size={15} />重命名</button>
      <button role="menuitem" disabled={props.disabled} onClick={() => { close(true); props.onPin(); }}><Icon name="pin" size={15} />{props.pinned ? '取消置顶' : '置顶'}</button>
      <button role="menuitem" disabled={props.disabled} onClick={() => { close(true); props.onArchive(); }}><Icon name="archive" size={15} />{props.archived ? '取消归档' : '归档'}</button>
      <button role="menuitem" className="session-menu-delete" disabled={props.disabled || props.deleteDisabled}
        title={props.deleteDisabled ? '请先停止运行中的会话' : undefined}
        onClick={() => { close(true); props.onDelete(); }}><Icon name="trash" size={15} />删除</button>
    </div>, document.body)}
  </>;
}
