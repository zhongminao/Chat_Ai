import type { CSSProperties } from 'react';

const paths = {
  refresh: 'M20 7v5h-5M4 17v-5h5M6.1 7a7 7 0 0 1 11.6-2L20 8M4 16l2.3 3A7 7 0 0 0 17.9 17',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  pin: 'm9 3 6 0-1 6 4 4H6l4-4-1-6ZM12 13v8',
  archive: 'M3 3h18v5H3ZM5 8v13h14V8M10 12h4',
  plus: 'M12 5v14M5 12h14',
  edit: 'm15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15l-1 6Z',
  check: 'm5 12 4 4L19 6',
  close: 'm6 6 12 12M6 18 18 6',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  menu: 'M4 6h16M4 12h16M4 18h16',
  arrow: 'M12 19V5m-6 6 6-6 6 6',
  down: 'm6 9 6 6 6-6',
  chat: 'M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-5 3V6a2 2 0 0 1 2-2Z',
  compact: 'M7 4H4v16h3M17 4h3v16h-3M8 9h8M8 12h6M8 15h8',
  tool: 'm14 6 4-4a6 6 0 0 1-7 8L4 17a2 2 0 0 0 3 3l7-7a6 6 0 0 0 8-7l-4 4-4-4Z',
  image: 'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm-2 13 5-5 4 4 3-3 6 6M8 7h.01',
};

export function Icon({ name, size = 18, style }: { name: keyof typeof paths; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>
    <path d={paths[name]} />
  </svg>;
}
