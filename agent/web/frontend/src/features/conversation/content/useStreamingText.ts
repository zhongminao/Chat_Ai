import { useEffect, useRef, useState } from 'react';

/** Smooth presentation only: the event state always retains the full source. */
export function useStreamingText(content: string, streaming: boolean): string {
  const [shown, setShown] = useState(() => streaming ? '' : content);
  const visible = useRef(shown);
  const target = useRef(content);
  const isStreaming = useRef(streaming);
  const wasStreaming = useRef(streaming);
  const frame = useRef<number | null>(null);
  const lastFrame = useRef(0);
  const lastArrival = useRef(performance.now());
  const rate = useRef(60);
  const credit = useRef(0);

  useEffect(() => {
    const now = performance.now();
    const added = content.length - target.current.length;
    if (streaming && added > 0) {
      const elapsed = Math.max((now - lastArrival.current) / 1000, .02);
      const observed = added / elapsed;
      rate.current = rate.current * .7 + observed * .3;
      lastArrival.current = now;
    }
    target.current = content;
    isStreaming.current = streaming;
    const immediate = window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      !content.startsWith(visible.current) || (!streaming && !wasStreaming.current && frame.current === null);
    wasStreaming.current = streaming;
    if (immediate) {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null; credit.current = 0;
      visible.current = content; setShown(content);
      return;
    }
    if (frame.current !== null || visible.current.length >= content.length) return;
    lastFrame.current = now;

    function advance(time: number) {
      frame.current = null;
      const remaining = target.current.length - visible.current.length;
      if (remaining <= 0) return;
      const gap = time - lastFrame.current;
      const elapsed = Math.min(Math.max(gap / 1000, 0), .05);
      lastFrame.current = time;
      // Follow measured arrival throughput, accelerating if a burst builds up.
      // Finishing a turn catches up faster. Resume background tabs at the source.
      if (gap > 500) {
        visible.current = target.current; credit.current = 0; setShown(visible.current);
        return;
      }
      const speed = Math.max(rate.current, remaining / (isStreaming.current ? .16 : .06));
      credit.current += speed * elapsed;
      const count = Math.min(remaining, Math.floor(credit.current));
      if (count > 0) {
        let end = visible.current.length + count;
        const last = target.current.charCodeAt(end - 1);
        if (end < target.current.length && last >= 0xd800 && last <= 0xdbff) end++;
        credit.current = Math.max(0, credit.current - (end - visible.current.length));
        visible.current = target.current.slice(0, end);
        setShown(visible.current);
      }
      if (visible.current.length < target.current.length) frame.current = requestAnimationFrame(advance);
    }
    frame.current = requestAnimationFrame(advance);
  }, [content, streaming]);

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
  }, []);
  return shown;
}
