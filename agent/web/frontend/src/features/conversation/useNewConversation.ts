import { useRef, useState } from 'react';
import { api } from '../../api/client';
import type { AccessMode, Model } from '../../api/types';
import { clearTextDraftIfUnchanged } from './textDraft';
import { removeNewConversationFiles, removeNewConversationImages, uploadNewConversationAttachments } from './newConversationAttachments';
import { errorMessage } from './useConversation';

/** One tab-local draft; a failed first send reuses its already-created session. */
export function useNewConversation(onSent: (id: string) => void, defaultModel: Model | null = null) {
  const session = useRef<string | null>(null);
  const pending = useRef(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setModel] = useState<Model | null>(null);
  const model = selectedModel ?? defaultModel;
  const [accessMode, setAccessMode] = useState<AccessMode>('full_access');

  async function send(text: string, imageIds: string[], fileIds: string[]) {
    if (pending.current) return false;
    pending.current = true; setSending(true); setError(null);
    try {
      session.current ??= (await api.createSession()).id;
      const id = session.current;
      if (model) await api.switchModel(id, model.provider, model.name);
      await api.accessMode(id, accessMode);
      const attachments = await uploadNewConversationAttachments(id, imageIds, fileIds);
      await api.send(id, text, attachments.images, attachments.files);
      clearTextDraftIfUnchanged(null, text);
      removeNewConversationImages(imageIds);
      removeNewConversationFiles(fileIds);
      session.current = null;
      onSent(id);
      return true;
    } catch (reason) {
      setError(errorMessage(reason));
      return false;
    } finally {
      pending.current = false; setSending(false);
    }
  }

  return { sending, error, model, accessMode, send,
    selectModel: async (provider: string, name: string) => { setModel({ provider, name }); return true; },
    setAccessMode,
  };
}
