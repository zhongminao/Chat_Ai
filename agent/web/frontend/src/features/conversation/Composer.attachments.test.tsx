import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps, ReactElement, ReactNode } from 'react';
import { api } from '../../api/client';
import { ImageAttachments } from '../images/ImageAttachments';
import { useImageDraft } from '../images/useImageDraft';
import { Composer } from './Composer';
import {
  getNewConversationFiles, getNewConversationImages, removeNewConversationFiles, removeNewConversationImages,
} from './newConversationAttachments';
import { useFileDraft } from './useFileDraft';

// Same hook harness as Composer.guidance.test.tsx; no DOM dependency is required.
const hooks = vi.hoisted(() => ({ values: [] as unknown[], index: 0 }));
vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useEffect: vi.fn(),
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

function findAll(node: ReactNode, type: unknown): ReactElement<Record<string, any>>[] {
  if (!node || typeof node !== 'object' || !('type' in node)) return [];
  const element = node as ReactElement<Record<string, any>>;
  return [
    ...(element.type === type ? [element] : []),
    ...[element.props.children].flat().flatMap(child => findAll(child, type)),
  ];
}

beforeEach(() => {
  hooks.values = []; hooks.index = 0;
  let index = 0;
  vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:local-${++index}`);
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
});
afterEach(() => {
  removeNewConversationImages(getNewConversationImages().map(image => image.id));
  removeNewConversationFiles(getNewConversationFiles().map(file => file.id));
  vi.restoreAllMocks();
});

function props(): ComponentProps<typeof Composer> {
  return {
    busy: false, ready: true, connected: true, readOnly: false, status: 'draft', pending: null,
    accessMode: 'full_access', accessDisabled: false, approvals: null, onAccessChange: vi.fn(),
    model: null, models: [], modelsRefreshing: false, modelsError: null, onRefreshModels: async () => {},
    sessionId: null, images: [], onUploaded: vi.fn(), onSend: vi.fn(async () => true),
    onGuide: vi.fn(async () => true), acceptedGuidance: [], onStop: vi.fn(async () => true),
    onModelChange: async () => true,
  };
}

describe('null-session composer attachments', () => {
  it('starts with full access and offers only audit or full access', () => {
    const view = Composer(props());
    const select = findAll(view, 'select')[0];
    expect(select.props.value).toBe('full_access');
    expect(findAll(select, 'option').map(option => option.props.value)).toEqual(['audit', 'full_access']);
  });

  it('stages image, file and folder inputs and restores them after visiting history', async () => {
    const p = props();
    const uploadImage = vi.spyOn(api, 'uploadImage');
    const uploadFile = vi.spyOn(api, 'uploadFile');
    const uploadFolder = vi.spyOn(api, 'uploadFolder');
    const render = () => { hooks.index = 0; return Composer(p); };
    const inputs = findAll(render(), 'input');
    const image = new File(['i'], 'image.png', { type: 'image/png' });
    const note = new File(['n'], 'note.txt');
    const nested = new File(['f'], 'nested.txt');
    Object.defineProperty(nested, 'webkitRelativePath', { value: 'project/sub/nested.txt' });
    for (const [index, file] of [image, note, nested].entries()) {
      inputs[index].props.onChange({ target: { files: [file], value: file.name } });
    }
    expect(getNewConversationImages()).toHaveLength(1);
    expect(getNewConversationFiles()).toHaveLength(2);
    expect(uploadImage).not.toHaveBeenCalled();
    expect(uploadFile).not.toHaveBeenCalled();
    expect(uploadFolder).not.toHaveBeenCalled();
    expect(p.onUploaded).not.toHaveBeenCalled();
    hooks.values = []; p.sessionId = 'history';
    expect(findAll(render(), ImageAttachments)[0].props.images).toEqual([]);
    expect(findAll(render(), 'span').filter(element => element.props.className === 'file-chip')).toHaveLength(0);
    hooks.values = []; p.sessionId = null;
    const restored = render();
    const attachments = findAll(restored, ImageAttachments)[0];
    expect(attachments.props.images).toEqual(getNewConversationImages());
    expect(attachments.props.previewUrls.get(attachments.props.images[0].id)).toBe('blob:local-1');
    expect(findAll(restored, 'span').filter(element => element.props.className === 'file-chip')).toHaveLength(2);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });

  it('retains local IDs after failed send and clears only the sent items on success', async () => {
    const p = props();
    p.onSend = vi.fn(async () => false);
    const render = () => { hooks.index = 0; return Composer(p); };
    const inputs = findAll(render(), 'input');
    inputs[0].props.onChange({ target: { files: [new File(['i'], 'image.png')], value: '' } });
    inputs[1].props.onChange({ target: { files: [new File(['f'], 'file.txt')], value: '' } });
    const imageIds = getNewConversationImages().map(image => image.id);
    const fileIds = getNewConversationFiles().map(file => file.id);
    const submit = async () => {
      findAll(render(), 'form')[0].props.onSubmit({ preventDefault: vi.fn() });
      await Promise.resolve();
      await Promise.resolve();
    };
    await submit();
    expect(p.onSend).toHaveBeenCalledWith('', imageIds, fileIds);
    expect(getNewConversationImages().map(image => image.id)).toEqual(imageIds);
    expect(getNewConversationFiles().map(file => file.id)).toEqual(fileIds);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    p.onSend = vi.fn(async () => true);
    await submit();
    expect(getNewConversationImages()).toEqual([]);
    expect(getNewConversationFiles()).toEqual([]);
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:local-1');
  });
});

describe('real-session attachment hooks', () => {
  it('keeps immediate uploads and server asset IDs for images, files and folders', async () => {
    const image = { id: 'server-image', name: 'a.png', filename: 'a.png', ordinal: 1,
      mime: 'image/png', width: 1, height: 1, size: 1 };
    const asset = { id: 'server-file', name: 'a.txt', filename: 'a.txt', path: '/a.txt', size: 1 };
    const folderAsset = { ...asset, id: 'server-folder', kind: 'folder' as const };
    const uploadImage = vi.spyOn(api, 'uploadImage').mockResolvedValue({ image });
    const uploadFile = vi.spyOn(api, 'uploadFile').mockResolvedValue({ file: asset });
    const uploadFolder = vi.spyOn(api, 'uploadFolder').mockResolvedValue({ file: folderAsset });
    const onUploaded = vi.fn();
    const render = () => {
      hooks.index = 0;
      return { images: useImageDraft('real', onUploaded), files: useFileDraft('real') };
    };
    const imageInput = new File(['i'], 'a.png');
    const fileInput = new File(['f'], 'a.txt');
    const folder = { name: 'project', entries: [{ file: fileInput, path: 'sub/a.txt' }] };
    await render().images.upload([imageInput]);
    await render().files.upload([fileInput]);
    await render().files.upload(folder);
    expect(uploadImage).toHaveBeenCalledExactlyOnceWith('real', imageInput);
    expect(uploadFile).toHaveBeenCalledExactlyOnceWith('real', fileInput);
    expect(uploadFolder).toHaveBeenCalledExactlyOnceWith('real', folder.name, folder.entries);
    expect(onUploaded).toHaveBeenCalledExactlyOnceWith(image);
    expect(render().images.ids).toEqual(['server-image']);
    expect(render().files.files).toEqual([asset, folderAsset]);
    expect(getNewConversationImages()).toEqual([]);
    expect(getNewConversationFiles()).toEqual([]);
  });
});
