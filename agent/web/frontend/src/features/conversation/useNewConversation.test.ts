import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Model } from '../../api/types';
import { api } from '../../api/client';
import { removeNewConversationFiles, removeNewConversationImages, uploadNewConversationAttachments } from './newConversationAttachments';
import { readTextDraft, writeTextDraft } from './textDraft';
import { useNewConversation } from './useNewConversation';

const hooks = vi.hoisted(() => ({ values: [] as unknown[], index: 0 }));
vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => { hooks.values[index] = value; }];
  },
  useRef(current: unknown) {
    const index = hooks.index++;
    return hooks.values[index] ??= { current };
  },
}));
vi.mock('../../api/client', () => ({ api: {
  createSession: vi.fn(), send: vi.fn(), switchModel: vi.fn(), accessMode: vi.fn(),
} }));
vi.mock('./newConversationAttachments', () => ({
  uploadNewConversationAttachments: vi.fn(), removeNewConversationFiles: vi.fn(), removeNewConversationImages: vi.fn(),
}));

const onSent = vi.fn();
function render(defaultModel: Model | null = null) { hooks.index = 0; return useNewConversation(onSent, defaultModel); }
beforeEach(() => {
  hooks.values = []; hooks.index = 0;
  vi.resetAllMocks();
  const store = new Map<string, string>();
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, text: string) => { store.set(key, text); },
    removeItem: (key: string) => { store.delete(key); },
  });
  writeTextDraft(null, 'draft');
  vi.mocked(api.createSession).mockResolvedValue({ id: 'real' });
  vi.mocked(api.send).mockResolvedValue({ accepted: true });
  vi.mocked(uploadNewConversationAttachments).mockResolvedValue({ images: ['uploaded-image'], files: ['uploaded-file'] });
});
afterEach(() => { writeTextDraft(null, ''); vi.unstubAllGlobals(); });

describe('first send from a local conversation draft', () => {
  it('shows the server default in the draft and preserves an explicit selection', async () => {
    expect(render().model).toBeNull();
    const defaultModel = { provider: 'gpt', name: 'gpt-6.1-sol' };
    expect(render(defaultModel).model).toEqual(defaultModel);
    expect(api.createSession).not.toHaveBeenCalled();
    await render(defaultModel).send('draft', [], []);
    expect(api.switchModel).toHaveBeenCalledExactlyOnceWith('real', 'gpt', 'gpt-6.1-sol');
    await render(defaultModel).selectModel('other', 'chosen');
    expect(render(defaultModel).model).toEqual({ provider: 'other', name: 'chosen' });
  });

  it('does not create a session when opening or choosing model and permissions', async () => {
    const draft = render();
    expect(draft.accessMode).toBe('full_access');
    await draft.selectModel('provider', 'model');
    draft.setAccessMode('audit');
    expect(render().model).toEqual({ provider: 'provider', name: 'model' });
    expect(render().accessMode).toBe('audit');
    expect(api.createSession).not.toHaveBeenCalled();
    expect(api.switchModel).not.toHaveBeenCalled();
    expect(api.accessMode).not.toHaveBeenCalled();
  });

  it('creates, uploads, sends real IDs, then clears captured drafts and selects the session', async () => {
    expect(await render().send('draft', ['local-image'], ['local-file'])).toBe(true);
    expect(api.createSession).toHaveBeenCalledTimes(1);
    expect(uploadNewConversationAttachments).toHaveBeenCalledExactlyOnceWith('real', ['local-image'], ['local-file']);
    expect(api.send).toHaveBeenCalledExactlyOnceWith('real', 'draft', ['uploaded-image'], ['uploaded-file']);
    expect(api.switchModel).not.toHaveBeenCalled();
    expect(api.accessMode).toHaveBeenCalledExactlyOnceWith('real', 'full_access');
    expect(readTextDraft(null)).toBe('');
    expect(removeNewConversationImages).toHaveBeenCalledExactlyOnceWith(['local-image']);
    expect(removeNewConversationFiles).toHaveBeenCalledExactlyOnceWith(['local-file']);
    expect(onSent).toHaveBeenCalledExactlyOnceWith('real');
    expect(render().sending).toBe(false);
  });

  it('applies explicit model and permission selections before uploading', async () => {
    await render().selectModel('provider', 'model');
    render().setAccessMode('audit');
    await render().send('draft', [], []);
    expect(api.switchModel).toHaveBeenCalledExactlyOnceWith('real', 'provider', 'model');
    expect(api.accessMode).toHaveBeenCalledExactlyOnceWith('real', 'audit');
    expect(vi.mocked(api.createSession).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.switchModel).mock.invocationCallOrder[0]);
    expect(vi.mocked(api.accessMode).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(uploadNewConversationAttachments).mock.invocationCallOrder[0]);
  });

  it.each(['upload', 'send'])('preserves drafts on %s failure and reuses the created session', async stage => {
    if (stage === 'upload') vi.mocked(uploadNewConversationAttachments).mockRejectedValueOnce(new Error('offline'));
    else vi.mocked(api.send).mockRejectedValueOnce(new Error('offline'));
    expect(await render().send('draft', ['local-image'], ['local-file'])).toBe(false);
    expect(render().error).toBe('offline');
    expect(readTextDraft(null)).toBe('draft');
    expect(onSent).not.toHaveBeenCalled();
    expect(removeNewConversationImages).not.toHaveBeenCalled();
    expect(removeNewConversationFiles).not.toHaveBeenCalled();
    expect(await render().send('draft', ['local-image'], ['local-file'])).toBe(true);
    expect(api.createSession).toHaveBeenCalledTimes(1);
    expect(render().error).toBeNull();
  });

  it('allows retry after creation fails without losing the draft', async () => {
    vi.mocked(api.createSession).mockRejectedValueOnce(new Error('offline'));
    expect(await render().send('draft', [], [])).toBe(false);
    expect(readTextDraft(null)).toBe('draft');
    expect(uploadNewConversationAttachments).not.toHaveBeenCalled();
    expect(await render().send('draft', [], [])).toBe(true);
    expect(api.createSession).toHaveBeenCalledTimes(2);
  });

  it('blocks concurrent sends and preserves text edited during an outstanding send', async () => {
    let finish!: (value: { accepted: boolean }) => void;
    vi.mocked(api.send).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    const first = render().send('draft', [], []);
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    expect(render().sending).toBe(true);
    expect(await render().send('duplicate', [], [])).toBe(false);
    writeTextDraft(null, 'next draft');
    finish({ accepted: true });
    expect(await first).toBe(true);
    expect(readTextDraft(null)).toBe('next draft');
    expect(api.createSession).toHaveBeenCalledTimes(1);
    expect(api.send).toHaveBeenCalledTimes(1);
    await render().send('next draft', [], []);
    expect(api.createSession).toHaveBeenCalledTimes(2);
  });
});
