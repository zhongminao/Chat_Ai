import { api } from '../../api/client';
import type { FileAsset, ImageAsset } from '../../api/types';
import type { SelectedFolder } from './folderEntries';

export const MAX_DRAFT_IMAGES = 8;
export const MAX_DRAFT_IMAGE_BYTES = 10 * 1024 * 1024;

export interface NewConversationImage extends ImageAsset {
  file: File;
  previewUrl: string;
}

interface UploadCache { uploads: Map<string, Promise<string>> }
interface ImageEntry extends UploadCache { image: NewConversationImage }
interface FileEntry extends UploadCache { asset: FileAsset; input: File | SelectedFolder }

// The null-session draft lives only in this browser tab's memory. These IDs identify
// attachments, never sessions; neither their IDs nor blob URLs go to api.send.
const images = new Map<string, ImageEntry>();
const files = new Map<string, FileEntry>();

export function getNewConversationImages(): NewConversationImage[] {
  return Array.from(images.values(), entry => entry.image);
}

export function getNewConversationFiles(): FileAsset[] {
  return Array.from(files.values(), entry => entry.asset);
}

export function addNewConversationImage(file: File): NewConversationImage {
  if (images.size >= MAX_DRAFT_IMAGES) throw new Error('每条消息最多包含 8 张图片');
  if (file.size > MAX_DRAFT_IMAGE_BYTES) throw new Error('单张图片不能超过 10 MB');
  const id = `new-image:${crypto.randomUUID()}`;
  const image: NewConversationImage = {
    id, name: file.name, filename: file.name, mime: file.type, size: file.size,
    ordinal: Math.max(0, ...getNewConversationImages().map(image => image.ordinal)) + 1,
    width: 0, height: 0, file, previewUrl: URL.createObjectURL(file),
  };
  images.set(id, { image, uploads: new Map() });
  return image;
}

export function addNewConversationFiles(input: File[] | SelectedFolder): FileAsset[] {
  const items: (File | SelectedFolder)[] = Array.isArray(input) ? input : [{
    name: input.name, entries: input.entries.map(entry => ({ ...entry })),
  }];
  return items.map(input => {
    const folder = 'entries' in input;
    const asset: FileAsset = {
      id: `new-file:${crypto.randomUUID()}`, name: input.name, filename: input.name,
      path: input.name, kind: folder ? 'folder' : 'file',
      size: folder ? input.entries.reduce((size, entry) => size + entry.file.size, 0) : input.size,
    };
    files.set(asset.id, { asset, input, uploads: new Map() });
    return asset;
  });
}

export function removeNewConversationImages(ids: string[]): void {
  for (const id of ids) {
    const entry = images.get(id);
    if (entry) URL.revokeObjectURL(entry.image.previewUrl);
    images.delete(id);
  }
}

export function removeNewConversationFiles(ids: string[]): void {
  for (const id of ids) files.delete(id);
}

function uploadOnce(entry: UploadCache, sessionId: string, upload: () => Promise<string>): Promise<string> {
  let pending = entry.uploads.get(sessionId);
  if (!pending) {
    pending = upload().catch(reason => {
      entry.uploads.delete(sessionId);
      throw reason;
    });
    // Keep fulfilled promises too: a failed send must not duplicate successful uploads.
    entry.uploads.set(sessionId, pending);
  }
  return pending;
}

/** Upload only the captured local IDs, preserving their order. Does not clear the
 * draft: the send flow removes these IDs only after sending succeeds. Uploads
 * are cached per real session (including in-flight requests); failures can retry.
 */
export async function uploadNewConversationAttachments(
  sessionId: string, imageIds: string[], fileIds: string[],
): Promise<{ images: string[]; files: string[] }> {
  if (!sessionId) throw new Error('上传附件需要真实会话');
  const selectedImages = imageIds.map(id => {
    const entry = images.get(id);
    if (!entry) throw new Error(`本地图片已不存在，请重新选择：${id}`);
    return entry;
  });
  const selectedFiles = fileIds.map(id => {
    const entry = files.get(id);
    if (!entry) throw new Error(`本地附件已不存在，请重新选择：${id}`);
    return entry;
  });
  const uploadedImages: string[] = [];
  const uploadedFiles: string[] = [];
  for (const entry of selectedImages) {
    uploadedImages.push(await uploadOnce(entry, sessionId, async () =>
      (await api.uploadImage(sessionId, entry.image.file)).image.id));
  }
  for (const entry of selectedFiles) {
    uploadedFiles.push(await uploadOnce(entry, sessionId, async () => {
      const input = entry.input;
      const result = 'entries' in input
        ? await api.uploadFolder(sessionId, input.name, input.entries)
        : await api.uploadFile(sessionId, input);
      return result.file.id;
    }));
  }
  return { images: uploadedImages, files: uploadedFiles };
}
