import { useRef, useState } from 'react';
import { api } from '../../api/client';
import type { FileAsset } from '../../api/types';

export function useFileDraft(sessionId: string | null) {
  const [files, setFiles] = useState<FileAsset[]>([]);
  const [uploading, setUploading] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const reportError = (reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason));

  async function upload(items: File[] | { name: string; entries: { file: File; path: string }[] }) {
    if (!sessionId || pending.current || (Array.isArray(items) ? !items.length : !items.entries.length)) return;
    pending.current = true; setUploading(true); setError(null);
    try {
      if (Array.isArray(items)) {
        for (const input of items) {
          const { file } = await api.uploadFile(sessionId, input);
          setFiles(current => [...current, file]);
        }
      } else {
        const { file } = await api.uploadFolder(sessionId, items.name, items.entries);
        setFiles(current => [...current, file]);
      }
    } catch (reason) {
      reportError(reason);
    } finally {
      pending.current = false; setUploading(false);
    }
  }

  const remove = (ids: string[]) => setFiles(current => current.filter(file => !ids.includes(file.id)));
  const restore = (items: FileAsset[]) => setFiles(current => [...current, ...items]);
  return { files, uploading, error, reportError, upload, remove, restore };
}
