import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps, ReactElement, ReactNode } from 'react';
import { Composer } from './Composer';
import { GuidanceQueue } from './GuidanceQueue';
import { writeTextDraft } from './textDraft';

const hooks = vi.hoisted(() => ({ values: [] as unknown[], index: 0, effects: [] as (() => void)[] }));
vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useEffect: vi.fn((callback: () => void) => { hooks.effects.push(callback); }),
  useLayoutEffect: vi.fn(),
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = typeof initial === 'function' ? initial() : initial;
    return [hooks.values[index], (value: unknown) => {
      hooks.values[index] = typeof value === 'function' ? value(hooks.values[index]) : value;
    }];
  },
  useRef(current: unknown) {
    const index = hooks.index++;
    return hooks.values[index] ??= { current };
  },
}));

function find(node: ReactNode, type: unknown): ReactElement<Record<string, any>> {
  if (node && typeof node === 'object' && 'type' in node) {
    const element = node as ReactElement<Record<string, any>>;
    if (element.type === type) return element;
    for (const child of [element.props.children].flat()) {
      try { return find(child, type); } catch { /* Try the next child. */ }
    }
  }
  throw new Error(`Missing element ${String(type)}`);
}

beforeEach(() => { hooks.values = []; hooks.index = 0; hooks.effects = []; });

describe('recalled guidance follows current execution state', () => {
  for (const busy of [false, true]) {
    it(busy ? 'queues recalled content while still running' : 'sends recalled content directly after completion, even with other queued drafts', async () => {
      const recalled = { id: 'recalled', text: '修改后的要求', images: ['image'], files: [{ id: 'file', name: 'notes.txt', path: '/notes.txt' }] };
      const other = { id: 'other', text: '保留在队列', images: [], files: [] };
      const store = new Map([['chat-ai:guidance:test', JSON.stringify([recalled, other])]]);
      vi.stubGlobal('sessionStorage', {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => { store.set(key, value); },
        removeItem: (key: string) => { store.delete(key); },
      });
      try {
        writeTextDraft('test', '');
        const props: ComponentProps<typeof Composer> = {
          busy: true, ready: true, connected: true, readOnly: false, status: 'running', pending: null,
          accessMode: 'audit', accessDisabled: false, approvals: null, onAccessChange: vi.fn(),
          model: null, models: [], modelsRefreshing: false, modelsError: null, onRefreshModels: async () => {},
          sessionId: 'test', images: [], onUploaded: vi.fn(), onSend: vi.fn(async () => true),
          onGuide: vi.fn(async () => true), acceptedGuidance: [], onStop: vi.fn(async () => true),
          onModelChange: async () => true,
        };
        const render = () => { hooks.index = 0; return Composer(props); };
        find(render(), GuidanceQueue).props.onEdit(recalled);
        props.busy = busy;
        const view = render();
        expect(find(view, 'textarea').props.value).toBe(recalled.text);
        find(view, 'form').props.onSubmit({ preventDefault: vi.fn() });
        await Promise.resolve();
        const queue = find(render(), GuidanceQueue).props.items;
        expect(queue[0]).toEqual(other);
        if (busy) {
          expect(props.onSend).not.toHaveBeenCalled();
          expect(queue).toHaveLength(2);
          expect(queue[1]).toMatchObject({ text: recalled.text, images: recalled.images, files: recalled.files });
        } else {
          expect(props.onSend).toHaveBeenCalledExactlyOnceWith(recalled.text, ['image'], ['file']);
          expect(queue).toEqual([other]);
        }
        expect(props.onGuide).not.toHaveBeenCalled();
      } finally {
        vi.unstubAllGlobals();
      }
    });
  }
});


describe('send while loading a switched session', () => {
  it('waits for readiness and connection before sending the original draft once', async () => {
    const store = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
      removeItem: (key: string) => { store.delete(key); },
    });
    try {
      writeTextDraft('loading', '待发送');
      const props: ComponentProps<typeof Composer> = {
        busy: false, ready: false, connected: false, readOnly: false, status: '正在连接', pending: null,
        accessMode: 'audit', accessDisabled: false, approvals: null, onAccessChange: vi.fn(),
        model: null, models: [], modelsRefreshing: false, modelsError: null, onRefreshModels: async () => {},
        sessionId: 'loading', images: [], onUploaded: vi.fn(), onSend: vi.fn(async () => true),
        onGuide: vi.fn(async () => true), acceptedGuidance: [], onStop: vi.fn(async () => true),
        onModelChange: async () => true,
      };
      const render = () => { hooks.index = 0; hooks.effects = []; return Composer(props); };
      const submit = () => find(render(), 'form').props.onSubmit({ preventDefault: vi.fn() });
      submit();
      expect(props.onSend).not.toHaveBeenCalled();
      props.ready = true;
      render(); hooks.effects.at(-1)!();
      expect(props.onSend).not.toHaveBeenCalled();
      props.connected = true;
      render(); hooks.effects.at(-1)!();
      await Promise.resolve();
      expect(props.onSend).toHaveBeenCalledExactlyOnceWith('待发送', [], []);
      expect(store.has('chat-ai:composer-draft:loading')).toBe(false);
      render(); hooks.effects.at(-1)!();
      expect(props.onSend).toHaveBeenCalledTimes(1);
    } finally { vi.unstubAllGlobals(); }
  });

  it('keeps the draft if sending fails after the session becomes ready', async () => {
    const store = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
      removeItem: (key: string) => { store.delete(key); },
    });
    try {
      writeTextDraft('loading', '失败后重试');
      const props: ComponentProps<typeof Composer> = {
        busy: false, ready: false, connected: false, readOnly: false, status: '正在连接', pending: null,
        accessMode: 'audit', accessDisabled: false, approvals: null, onAccessChange: vi.fn(),
        model: null, models: [], modelsRefreshing: false, modelsError: null, onRefreshModels: async () => {},
        sessionId: 'loading', images: [], onUploaded: vi.fn(), onSend: vi.fn(async () => false),
        onGuide: vi.fn(async () => true), acceptedGuidance: [], onStop: vi.fn(async () => true),
        onModelChange: async () => true,
      };
      const render = () => { hooks.index = 0; hooks.effects = []; return Composer(props); };
      find(render(), 'form').props.onSubmit({ preventDefault: vi.fn() });
      props.ready = true; props.connected = true;
      render(); hooks.effects.at(-1)!();
      await Promise.resolve();
      expect(props.onSend).toHaveBeenCalledTimes(1);
      expect(store.get('chat-ai:composer-draft:loading')).toBe('失败后重试');
      render(); hooks.effects.at(-1)!();
      expect(props.onSend).toHaveBeenCalledTimes(1);
    } finally { vi.unstubAllGlobals(); }
  });

  it('cancels the deferred send when the user edits the draft', () => {
    const store = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
      removeItem: (key: string) => { store.delete(key); },
    });
    try {
      writeTextDraft('loading', '之前的草稿');
      const props: ComponentProps<typeof Composer> = {
        busy: false, ready: false, connected: false, readOnly: false, status: '正在连接', pending: null,
        accessMode: 'audit', accessDisabled: false, approvals: null, onAccessChange: vi.fn(),
        model: null, models: [], modelsRefreshing: false, modelsError: null, onRefreshModels: async () => {},
        sessionId: 'loading', images: [], onUploaded: vi.fn(), onSend: vi.fn(async () => true),
        onGuide: vi.fn(async () => true), acceptedGuidance: [], onStop: vi.fn(async () => true),
        onModelChange: async () => true,
      };
      const render = () => { hooks.index = 0; hooks.effects = []; return Composer(props); };
      find(render(), 'form').props.onSubmit({ preventDefault: vi.fn() });
      find(render(), 'textarea').props.onChange({ target: { value: '新草稿' } });
      props.ready = true; props.connected = true;
      render(); hooks.effects.at(-1)!();
      expect(props.onSend).not.toHaveBeenCalled();
      expect(store.get('chat-ai:composer-draft:loading')).toBe('新草稿');
    } finally { vi.unstubAllGlobals(); }
  });

  for (const changed of ['busy', 'readOnly'] as const) {
    it(`keeps the draft and does not turn a delayed send into ${changed}`, () => {
      const store = new Map<string, string>();
      vi.stubGlobal('sessionStorage', {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => { store.set(key, value); },
        removeItem: (key: string) => { store.delete(key); },
      });
      try {
        writeTextDraft('loading', '留在草稿');
        const props: ComponentProps<typeof Composer> = {
          busy: false, ready: false, connected: false, readOnly: false, status: '正在连接', pending: null,
          accessMode: 'audit', accessDisabled: false, approvals: null, onAccessChange: vi.fn(),
          model: null, models: [], modelsRefreshing: false, modelsError: null, onRefreshModels: async () => {},
          sessionId: 'loading', images: [], onUploaded: vi.fn(), onSend: vi.fn(async () => true),
          onGuide: vi.fn(async () => true), acceptedGuidance: [], onStop: vi.fn(async () => true),
          onModelChange: async () => true,
        };
        const render = () => { hooks.index = 0; hooks.effects = []; return Composer(props); };
        find(render(), 'form').props.onSubmit({ preventDefault: vi.fn() });
        props[changed] = true;
        props.ready = true; props.connected = true;
        render(); hooks.effects.at(-1)!();
        expect(props.onSend).not.toHaveBeenCalled();
        expect(props.onGuide).not.toHaveBeenCalled();
        expect(props.onStop).not.toHaveBeenCalled();
        expect(store.get('chat-ai:composer-draft:loading')).toBe('留在草稿');
      } finally { vi.unstubAllGlobals(); }
    });
  }

  it('abandons the pending send on composer remount for another session', () => {
    const store = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
      removeItem: (key: string) => { store.delete(key); },
    });
    try {
      writeTextDraft('old', '原会话草稿');
      const props: ComponentProps<typeof Composer> = {
        busy: false, ready: false, connected: false, readOnly: false, status: '正在连接', pending: null,
        accessMode: 'audit', accessDisabled: false, approvals: null, onAccessChange: vi.fn(),
        model: null, models: [], modelsRefreshing: false, modelsError: null, onRefreshModels: async () => {},
        sessionId: 'old', images: [], onUploaded: vi.fn(), onSend: vi.fn(async () => true),
        onGuide: vi.fn(async () => true), acceptedGuidance: [], onStop: vi.fn(async () => true),
        onModelChange: async () => true,
      };
      const render = () => { hooks.index = 0; hooks.effects = []; return Composer(props); };
      find(render(), 'form').props.onSubmit({ preventDefault: vi.fn() });
      hooks.values = []; // App keys Composer by sessionId, so switching remounts it.
      props.sessionId = 'new'; props.ready = true; props.connected = true;
      render(); hooks.effects.at(-1)!();
      expect(props.onSend).not.toHaveBeenCalled();
      expect(store.get('chat-ai:composer-draft:old')).toBe('原会话草稿');
    } finally { vi.unstubAllGlobals(); }
  });
});
