import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../api/client';
import {
  addNewConversationFiles, addNewConversationImage, getNewConversationFiles, getNewConversationImages,
  MAX_DRAFT_IMAGE_BYTES, removeNewConversationFiles, removeNewConversationImages, uploadNewConversationAttachments,
} from './newConversationAttachments';

beforeEach(() => {
  let index = 0;
  vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:local-${++index}`);
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
});
afterEach(() => {
  removeNewConversationImages(getNewConversationImages().map(image => image.id));
  removeNewConversationFiles(getNewConversationFiles().map(file => file.id));
  vi.restoreAllMocks();
});

const imageAsset = (id: string) => ({ id, name: 'a.png', filename: 'a.png', ordinal: 1,
  mime: 'image/png', width: 1, height: 1, size: 1 });
const fileAsset = (id: string) => ({ id, name: 'a.txt', filename: 'a.txt', path: '/a.txt', size: 1 });

describe('new conversation attachments', () => {
  it('stages original files and folder entries without contacting the backend', () => {
    const uploadImage = vi.spyOn(api, 'uploadImage');
    const uploadFile = vi.spyOn(api, 'uploadFile');
    const uploadFolder = vi.spyOn(api, 'uploadFolder');
    const image = new File(['image'], 'image.png', { type: 'image/png' });
    const file = new File(['notes'], 'notes.txt');
    const stagedImage = addNewConversationImage(image);
    const stagedFiles = addNewConversationFiles([file]);
    const stagedFolder = addNewConversationFiles({ name: 'project', entries: [{ file, path: 'nested/notes.txt' }] });
    expect(stagedImage).toMatchObject({ file: image, previewUrl: 'blob:local-1' });
    expect(stagedImage.id).toMatch(/^new-image:/);
    expect(stagedFiles[0].id).toMatch(/^new-file:/);
    expect(getNewConversationImages()).toEqual([stagedImage]);
    expect(getNewConversationFiles()).toEqual([...stagedFiles, ...stagedFolder]);
    expect(stagedFolder[0]).toMatchObject({ kind: 'folder', name: 'project', size: file.size });
    expect(uploadImage).not.toHaveBeenCalled();
    expect(uploadFile).not.toHaveBeenCalled();
    expect(uploadFolder).not.toHaveBeenCalled();
  });

  it('maps only requested IDs in order and retains drafts until explicit removal', async () => {
    const image = new File(['i'], 'a.png', { type: 'image/png' });
    const a = addNewConversationImage(image);
    const unused = addNewConversationImage(image);
    const input = new File(['a'], 'a.txt');
    const [file] = addNewConversationFiles([input]);
    const entries = [{ file: input, path: 'sub/a.txt' }];
    const [folder] = addNewConversationFiles({ name: 'project', entries });
    const uploadImage = vi.spyOn(api, 'uploadImage').mockResolvedValue({ image: imageAsset('image-real') });
    const uploadFile = vi.spyOn(api, 'uploadFile').mockResolvedValue({ file: fileAsset('file-real') });
    const uploadFolder = vi.spyOn(api, 'uploadFolder').mockResolvedValue({ file: fileAsset('folder-real') });
    expect(await uploadNewConversationAttachments('session', [a.id], [folder.id, file.id])).toEqual({
      images: ['image-real'], files: ['folder-real', 'file-real'],
    });
    expect(uploadImage).toHaveBeenCalledExactlyOnceWith('session', image);
    expect(uploadFile).toHaveBeenCalledExactlyOnceWith('session', input);
    expect(uploadFolder).toHaveBeenCalledExactlyOnceWith('session', 'project', entries);
    expect(getNewConversationImages().map(image => image.id)).toEqual([a.id, unused.id]);
    expect(getNewConversationFiles()).toHaveLength(2);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    removeNewConversationImages([a.id]);
    removeNewConversationFiles([file.id, folder.id]);
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith(a.previewUrl);
    expect(getNewConversationImages()).toEqual([unused]);
    expect(getNewConversationFiles()).toEqual([]);
  });

  it('retries failed uploads but reuses successful uploads after upload or send failure', async () => {
    const image = addNewConversationImage(new File(['i'], 'a.png'));
    const [file] = addNewConversationFiles([new File(['f'], 'a.txt')]);
    const uploadImage = vi.spyOn(api, 'uploadImage').mockResolvedValue({ image: imageAsset('image-real') });
    const uploadFile = vi.spyOn(api, 'uploadFile').mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ file: fileAsset('file-real') });
    const upload = () => uploadNewConversationAttachments('session', [image.id], [file.id]);
    await expect(upload()).rejects.toThrow('offline');
    expect(getNewConversationFiles()).toHaveLength(1);
    await expect(upload()).resolves.toEqual({ images: ['image-real'], files: ['file-real'] });
    // Simulate api.send failing after all uploads succeeded.
    await expect(upload()).resolves.toEqual({ images: ['image-real'], files: ['file-real'] });
    expect(uploadImage).toHaveBeenCalledTimes(1);
    expect(uploadFile).toHaveBeenCalledTimes(2);
    await uploadNewConversationAttachments('different-session', [image.id], [file.id]);
    expect(uploadImage).toHaveBeenCalledTimes(2);
    expect(uploadFile).toHaveBeenCalledTimes(3);
  });

  it('shares concurrent uploads and permits retrying a failed image', async () => {
    const image = addNewConversationImage(new File(['i'], 'a.png'));
    const uploadImage = vi.spyOn(api, 'uploadImage').mockRejectedValueOnce(new Error('image failed'));
    await expect(uploadNewConversationAttachments('session', [image.id], [])).rejects.toThrow('image failed');
    let finish!: (value: { image: ReturnType<typeof imageAsset> }) => void;
    uploadImage.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const first = uploadNewConversationAttachments('session', [image.id], []);
    const second = uploadNewConversationAttachments('session', [image.id], []);
    expect(uploadImage).toHaveBeenCalledTimes(2);
    finish({ image: imageAsset('real') });
    expect(await first).toEqual({ images: ['real'], files: [] });
    expect(await second).toEqual(await first);
  });

  it('does not upload anything for missing IDs or an empty selection', async () => {
    const image = addNewConversationImage(new File(['i'], 'a.png'));
    const uploadImage = vi.spyOn(api, 'uploadImage');
    await expect(uploadNewConversationAttachments('session', [image.id], ['missing'])).rejects.toThrow('本地附件已不存在');
    await expect(uploadNewConversationAttachments('session', ['missing'], [])).rejects.toThrow('本地图片已不存在');
    await expect(uploadNewConversationAttachments('', [], [])).rejects.toThrow('真实会话');
    await expect(uploadNewConversationAttachments('session', [], [])).resolves.toEqual({ images: [], files: [] });
    expect(uploadImage).not.toHaveBeenCalled();
  });

  it('keeps the eight-image and ten-MB rules and revokes each removed preview once', () => {
    const tooLarge = new File([new Uint8Array(MAX_DRAFT_IMAGE_BYTES + 1)], 'large.png');
    expect(() => addNewConversationImage(tooLarge)).toThrow('10 MB');
    const limit = addNewConversationImage(new File([new Uint8Array(MAX_DRAFT_IMAGE_BYTES)], 'limit.png'));
    for (let index = 1; index < 8; index++) addNewConversationImage(new File(['i'], `${index}.png`));
    expect(() => addNewConversationImage(new File(['i'], 'ninth.png'))).toThrow('8 张');
    expect(URL.createObjectURL).toHaveBeenCalledTimes(8);
    removeNewConversationImages([limit.id, limit.id]);
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith(limit.previewUrl);
    expect(() => addNewConversationImage(new File(['i'], 'replacement.png'))).not.toThrow();
  });
});
