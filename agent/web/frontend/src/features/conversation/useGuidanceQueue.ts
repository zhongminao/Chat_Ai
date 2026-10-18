import { useEffect, useState } from 'react';

export interface GuidanceDraft { id: string; text: string; images: string[] }

export function useGuidanceQueue(sessionId: string | null, accepted: string[]) {
  const key = `chat-ai:guidance:${sessionId}`;
  const [items, setItems] = useState<GuidanceDraft[]>(() => {
    try {
      const saved: unknown = JSON.parse(sessionStorage.getItem(key) ?? '[]');
      return Array.isArray(saved) ? saved.filter(item => typeof item?.id === 'string' &&
        typeof item.text === 'string' && Array.isArray(item.images) && item.images.every((id: unknown) => typeof id === 'string')) : [];
    } catch { return []; }
  });
  useEffect(() => {
    try { sessionStorage.setItem(key, JSON.stringify(items)); } catch { /* Storage may be unavailable. */ }
  }, [key, items]);
  const acceptedKey = accepted.join('|');
  useEffect(() => {
    const ids = new Set(acceptedKey.split('|'));
    setItems(current => {
      const remaining = current.filter(item => !ids.has(item.id));
      return remaining.length === current.length ? current : remaining;
    });
  }, [acceptedKey]);
  return {
    items,
    add: (text: string, images: string[]) => setItems(current => [...current, { id: crypto.randomUUID(), text, images }]),
    remove: (id: string) => setItems(current => current.filter(item => item.id !== id)),
  };
}
