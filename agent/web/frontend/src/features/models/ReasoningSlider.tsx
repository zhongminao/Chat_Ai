import { type PointerEvent, type ReactNode, useEffect, useRef, useState } from 'react';

const effortLabel = (value: string) => ({ none: '无', minimal: '极低', low: '低', medium: '中', high: '高', xhigh: '最高', max: '最高' })[value] ?? value;

export function ReasoningSlider({ levels, value, disabled, onSelect, heading }: {
  levels: string[]; value: string; disabled: boolean;
  onSelect: (value: string) => Promise<void>; heading: (label: string) => ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const tracking = useRef<AbortController | null>(null);
  useEffect(() => () => tracking.current?.abort(), []);
  const [position, setPosition] = useState<number | null>(null);
  const end = levels.length - 1;
  const selected = Math.max(0, levels.indexOf(value));
  const current = position ?? selected;
  async function finish(next?: number) {
    setPosition(next ?? null);
    try { if (next !== undefined && next !== selected) await onSelect(levels[next]); }
    finally { setPosition(null); }
  }
  function startDrag(event: PointerEvent<HTMLDivElement>) {
    if (disabled || event.button !== 0 || !event.isPrimary || tracking.current) return;
    event.preventDefault(); input.current?.focus({ preventScroll: true });
    const pointer = event.pointerId, rect = event.currentTarget.getBoundingClientRect();
    const positionAt = (x: number) => Math.max(0, Math.min(end, (x - rect.left - 13) / Math.max(1, rect.width - 26) * end));
    const controller = tracking.current = new AbortController();
    const options = { signal: controller.signal };
    function stop(next?: number) { controller.abort(); tracking.current = null; void finish(next); }
    setPosition(positionAt(event.clientX));
    window.addEventListener('pointermove', e => { if (e.pointerId === pointer) setPosition(positionAt(e.clientX)); }, options);
    window.addEventListener('pointerup', e => { if (e.pointerId === pointer) stop(Math.round(positionAt(e.clientX))); }, options);
    window.addEventListener('pointercancel', e => { if (e.pointerId === pointer) stop(); }, options);
    window.addEventListener('blur', () => stop(), options);
  }
  const ratio = current / end;
  const fill = `calc(${ratio * 100}% + ${13 - 26 * ratio}px)`;
  const label = effortLabel(levels[Math.round(current)]);
  return <>{heading(label)}<div className="reasoning-slider" style={{ background: `linear-gradient(to right, #3297f4 ${fill}, #e7e7e8 ${fill})` }}
    onPointerDown={startDrag}>
    <div className="reasoning-ticks" aria-hidden="true">{levels.map((level, index) => <i key={level} className={index <= current ? 'passed' : ''} />)}</div>
    <input ref={input} type="range" aria-label="推理强度" aria-valuetext={label}
      min={0} max={end} step="any" value={current} disabled={disabled} onChange={event => void finish(Math.round(Number(event.target.value)))}
      onKeyDown={event => {
        const delta = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -1, PageUp: 1 }[event.key];
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? end : delta === undefined ? null : Math.max(0, Math.min(end, selected + delta));
        if (next !== null) { event.preventDefault(); void finish(next); }
      }} />
  </div></>;
}
