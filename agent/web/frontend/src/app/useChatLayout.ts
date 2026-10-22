import { useLayoutEffect, useRef } from 'react';

// Keep the native scroll rail uncovered and reserve the measured overlay sizes.
export function useChatLayout(sessionId: string | null) {
  const workspace = useRef<HTMLElement>(null);
  const top = useRef<HTMLDivElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const viewport = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const root = workspace.current;
    const header = top.current;
    const footer = bottom.current;
    const scroll = viewport.current;
    if (!root || !header || !footer || !scroll) return;
    let previousTop: number | undefined;
    const measure = () => {
      const atBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight <= 2;
      const composer = footer.firstElementChild as HTMLElement | null;
      root.style.setProperty('--chat-footer-limit', `${root.clientHeight * 0.65}px`);
      footer.classList.toggle('is-tall', Boolean(composer && composer.scrollHeight > root.clientHeight * 0.65));
      const height = header.getBoundingClientRect().height;
      root.style.setProperty('--chat-top', `${height}px`);
      root.style.setProperty('--chat-bottom', `${footer.getBoundingClientRect().height}px`);
      root.style.setProperty('--chat-rail', `${scroll.offsetWidth - scroll.clientWidth}px`);
      // A banner appearing above the messages must not displace the text being read.
      if (atBottom) scroll.scrollTop = scroll.scrollHeight;
      else if (previousTop !== undefined) scroll.scrollTop += height - previousTop;
      previousTop = height;
    };
    measure();
    const observer = new ResizeObserver(measure);
    [root, header, footer, scroll].forEach(element => observer.observe(element));
    if (footer.firstElementChild) observer.observe(footer.firstElementChild);
    return () => observer.disconnect();
  }, [sessionId]);

  return { workspace, top, bottom, viewport };
}
