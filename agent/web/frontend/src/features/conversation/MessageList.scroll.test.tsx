import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';
import { MessageList } from './MessageList';
import { ToolCallCard } from './ToolCallCard';

// Exercise component handlers and layout/resize paths without a DOM dependency.
const hooks = vi.hoisted(() => ({ refs: [] as { current: unknown }[], index: 0,
  layouts: [] as (() => void)[], effects: [] as (() => void)[] }));
vi.mock('react', async importOriginal => ({
  ...await importOriginal<typeof import('react')>(),
  useRef(value: unknown) {
    const index = hooks.index++;
    return hooks.refs[index] ?? (hooks.refs[index] = { current: value });
  },
  useState: (value: unknown) => [value, () => {}],
  useLayoutEffect: (effect: () => void) => { hooks.layouts.push(effect); },
  useEffect: (effect: () => void) => { hooks.effects.push(effect); },
}));

type Node = ReactElement<Record<string, any>>;
function find(node: Node, predicate: (node: Node) => boolean): Node | undefined {
  if (!node || typeof node !== 'object') return;
  if (predicate(node)) return node;
  const children = [node.props?.children].flat(Infinity) as Node[];
  for (const child of children) {
    const found = find(child, predicate);
    if (found) return found;
  }
}

let resize: () => void;
let viewport: { scrollTop: number; scrollHeight: number; clientHeight: number };
function render() {
  hooks.index = 0;
  hooks.layouts = [];
  hooks.effects = [];
  const tree = MessageList({
    items: [{ id: 'tool:1', kind: 'tool', name: 'read_file', status: 'running' }],
    busy: true, loading: false, assistantId: null, sessionId: 'test', images: [],
  }) as Node;
  const log = find(tree, node => node.props?.role === 'log')!;
  log.props.ref.current = viewport;
  find(tree, node => node.props?.className === 'message-body')!.props.ref.current = {};
  hooks.layouts.forEach(effect => effect());
  hooks.effects.forEach(effect => effect());
  return { scroll: () => log.props.onScroll(),
    inspect: () => find(tree, node => node.type === ToolCallCard)!.props.onInspect() };
}

beforeEach(() => {
  hooks.refs = [];
  viewport = { scrollTop: 600, scrollHeight: 1000, clientHeight: 400 };
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resize = callback; }
    observe() {}
    disconnect() {}
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('tool inspection scrolling', () => {
  it('does not pull the viewport back to an inspected tool when messages grow', () => {
    const view = render();
    view.inspect();
    viewport.scrollTop = 200;
    view.scroll();
    viewport.scrollHeight = 1300;
    render();
    resize();
    expect(viewport.scrollTop).toBe(200);
  });

  it('resumes following after manually scrolling to the bottom of an inspected tool', () => {
    const view = render();
    view.inspect();
    // The initial layout assigned scrollHeight; emulate the browser clamp.
    viewport.scrollTop = 600;
    view.scroll();
    viewport.scrollHeight = 1300;
    resize();
    expect(viewport.scrollTop).toBe(1300);
    viewport.scrollHeight = 1500;
    render();
    expect(viewport.scrollTop).toBe(1500);
  });

  it('does not resume following while still above the bottom', () => {
    const view = render();
    view.inspect();
    viewport.scrollTop = 560;
    view.scroll();
    viewport.scrollHeight = 1300;
    resize();
    expect(viewport.scrollTop).toBe(560);
  });
});
