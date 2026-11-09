import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { ImageAsset } from '../../api/types';
import { addNewConversationImage, getNewConversationImages, removeNewConversationImages,
  MAX_DRAFT_IMAGES, MAX_DRAFT_IMAGE_BYTES } from '../conversation/newConversationAttachments';

export function useImageDraft(sessionId: string | null, onUploaded: (image: ImageAsset) => void) {
  const [ids, setIds] = useState<string[]>(() => sessionId === null ? getNewConversationImages().map(image => image.id) : []);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = useRef(ids); current.current = ids;
  const notify = useRef(onUploaded); notify.current = onUploaded;
  const alive = useRef(true);
  const pending = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  async function upload(files: File[]) {
    if (!files.length || pending.current) return;
    pending.current = true; setUploading(true); setError(null);
    try {
      for (const file of files) {
        if (!alive.current) return;
        if (current.current.length >= MAX_DRAFT_IMAGES) throw new Error('每条消息最多包含 8 张图片');
        if (file.size > MAX_DRAFT_IMAGE_BYTES) throw new Error('单张图片不能超过 10 MB');
        const image = sessionId === null ? addNewConversationImage(file) : (await api.uploadImage(sessionId, file)).image;
        if (!alive.current) return;
        if (sessionId !== null) notify.current(image);
        current.current = [...current.current, image.id];
        setIds(current.current);
      }
    } catch (error) {
      if (alive.current) setError(error instanceof Error ? error.message : String(error));
    } finally {
      pending.current = false;
      if (alive.current) setUploading(false);
    }
  }

  function remove(sent: string[]) {
    if (sessionId === null) removeNewConversationImages(sent);
    current.current = current.current.filter(id => !sent.includes(id));
    setIds(current.current);
  }

  function restore(images: string[]) {
    current.current = [...images];
    setIds(current.current);
  }

  return { ids, localImages: sessionId === null ? getNewConversationImages() : [], uploading, error, upload, remove, restore };
}
