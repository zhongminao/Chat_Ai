import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearTextDraftIfUnchanged, readTextDraft, writeTextDraft } from './textDraft';

const store = new Map<string, string>();
beforeEach(() => {
  store.clear();
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, value); },
    removeItem: (key: string) => { store.delete(key); },
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('per-session composer draft', () => {
  it('keeps unsent text when switching sessions and returning', () => {
    writeTextDraft('new', '尚未发送');
    writeTextDraft('other', '另一个草稿');
    expect(readTextDraft('other')).toBe('另一个草稿');
    expect(readTextDraft('new')).toBe('尚未发送');
    writeTextDraft(null, '新会话草稿');
    expect(readTextDraft(null)).toBe('新会话草稿');
    expect(readTextDraft('new')).toBe('尚未发送');
    writeTextDraft(null, '');
  });

  it('clears only successful sends of unchanged text', () => {
    writeTextDraft('new', '原消息');
    writeTextDraft('new', '发送期间新输入');
    expect(clearTextDraftIfUnchanged('new', '原消息')).toBe(false);
    expect(readTextDraft('new')).toBe('发送期间新输入');
    expect(clearTextDraftIfUnchanged('new', '发送期间新输入')).toBe(true);
    expect(readTextDraft('new')).toBe('');
    expect(store.has('chat-ai:composer-draft:new')).toBe(false);
  });

  it('restores the new-conversation draft from tab storage and clears only unchanged sends', () => {
    store.set('chat-ai:new-conversation-text', '刷新前输入');
    expect(readTextDraft(null)).toBe('刷新前输入');
    writeTextDraft(null, '发送期间新输入');
    expect(clearTextDraftIfUnchanged(null, '刷新前输入')).toBe(false);
    expect(readTextDraft(null)).toBe('发送期间新输入');
    expect(clearTextDraftIfUnchanged(null, '发送期间新输入')).toBe(true);
    expect(store.has('chat-ai:new-conversation-text')).toBe(false);
  });

  it('keeps a draft in memory when browser storage is unavailable', () => {
    vi.stubGlobal('sessionStorage', { getItem: () => { throw Error('blocked'); }, setItem: () => { throw Error('blocked'); }, removeItem: () => { throw Error('blocked'); } });
    writeTextDraft('private', 'still here');
    expect(readTextDraft('private')).toBe('still here');
    writeTextDraft('private', '');
  });
});
