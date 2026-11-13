import { useRef, type ReactNode } from 'react';

// Only a press-and-release in place toggles. Drag selection must stay selection.
export function DisclosureSummary({ children, onToggle, title }: {
  children: ReactNode; onToggle: () => void; title?: string;
}) {
  const press = useRef<{ x: number; y: number } | null>(null);
  const clicked = useRef(false);
  return <summary title={title}
    onPointerDown={event => {
      clicked.current = false;
      press.current = event.button === 0 ? { x: event.clientX, y: event.clientY } : null;
    }}
    onPointerMove={event => {
      if (press.current && Math.hypot(event.clientX - press.current.x, event.clientY - press.current.y) > 5) press.current = null;
    }}
    onPointerUp={event => {
      const bounds = event.currentTarget.getBoundingClientRect();
      clicked.current = Boolean(press.current
        && Math.hypot(event.clientX - press.current.x, event.clientY - press.current.y) <= 5
        && event.clientX >= bounds.left && event.clientX <= bounds.right
        && event.clientY >= bounds.top && event.clientY <= bounds.bottom);
      press.current = null;
    }}
    onPointerCancel={() => { press.current = null; clicked.current = false; }}
    onClick={event => {
      event.preventDefault();
      if ((event.detail === 0 || clicked.current) && !window.getSelection()?.toString()) onToggle();
      clicked.current = false;
    }}>{children}</summary>;
}
