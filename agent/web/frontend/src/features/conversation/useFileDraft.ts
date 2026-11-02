import { useRef, useState } from 'react';
import { api } from '../../api/client';
import type { FileAsset } from '../../api/types';

export function useFileDraft(sessionId: string | null) {
  const [files, setFiles] = useState<FileAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(selected: File[]) {
    if (!sessionId || !selected.length || pending.current) return;
    pending.current = true; setUploading(true); setError(null);
    try {
      for (const input of selected) {
        const { file } = await api.uploadFile(sessionId, input);
        setFiles(current => [...current, file]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      pending.current = false; setUploading(false);
    }
  }

  const remove = (ids: string[]) => setFiles(current => current.filter(file => !ids.includes(file.id)));
  const restore = (items: FileAsset[]) => setFiles(current => [...current, ...items]);
  return { files, uploading, error, upload, remove, restore };
}
