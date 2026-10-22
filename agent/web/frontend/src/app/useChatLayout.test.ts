import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useChatLayout } from './useChatLayout';

const hooks = vi.hoisted(() => ({ effects: [] as (() => void | (() => void))[] }));
vi.mock('react', () => ({
  useRef: () => ({ current: null }),
  useLayoutEffect: (effect: () => void) => hooks.effects.push(effect),
}));

beforeEach(() => {
  hooks.effects = [];
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
});
afterEach(() => vi.unstubAllGlobals());

describe('chat overlay layout', () => {
  it.each([0, 15, 24])('leaves the full scroll rail uncovered for a %ipx native gutter', gutter => {
    const layout = useChatLayout('test');
    const properties = new Map<string, string>();
    const root = { clientHeight: 800, style: { setProperty: (key: string, value: string) => properties.set(key, value) } };
    const header = { getBoundingClientRect: () => ({ height: 64 }) };
    const footer = { firstElementChild: { scrollHeight: 180 }, classList: { toggle: vi.fn() },
      getBoundingClientRect: () => ({ height: 180 }) };
    const viewport = { offsetWidth: 1000, clientWidth: 1000 - gutter, clientHeight: 800, scrollHeight: 2000, scrollTop: 1200 };
    Object.assign(layout.workspace, { current: root });
    Object.assign(layout.top, { current: header });
    Object.assign(layout.bottom, { current: footer });
    Object.assign(layout.viewport, { current: viewport });
    const cleanup = hooks.effects[0]();
    expect(properties.get('--chat-rail')).toBe(`${Math.max(16, gutter)}px`);
    expect(properties.get('--chat-top')).toBe('64px');
    expect(properties.get('--chat-bottom')).toBe('180px');
    expect(viewport.scrollTop).toBe(2000);
    cleanup?.();
  });
});
