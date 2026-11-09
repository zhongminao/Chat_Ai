import { useEffect, useState } from 'react';
import type { SessionSummary } from '../../api/types';

const storageKey = 'chat-ai:session-read:v1';
type ReadState = Record<string, number>;

export function readSessionCursors(): ReadState {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(([, seq]) => typeof seq === 'number' && Number.isSafeInteger(seq) && seq >= 0));
  } catch { return {}; }
}

export function sessionIndicator(session: SessionSummary, readThrough = 0): 'running' | 'failed' | 'unread' | null {
  if (session.busy) return 'running';
  if ((session.activitySeq ?? 0) <= readThrough) return null;
  if (session.status === 'failed') return 'failed';
  return 'unread';
}

export function useSessionReadState(selected: string | null, ready: boolean, seq: number) {
  const [readThrough, setReadThrough] = useState(readSessionCursors);
  const [focused, setFocused] = useState(() => document.visibilityState === 'visible' && document.hasFocus());
  useEffect(() => {
    const update = () => setFocused(document.visibilityState === 'visible' && document.hasFocus());
    window.addEventListener('focus', update);
    window.addEventListener('blur', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      window.removeEventListener('focus', update);
      window.removeEventListener('blur', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, []);
  useEffect(() => {
    if (!selected || !ready || !focused || seq <= (readThrough[selected] ?? 0)) return;
    const next = { ...readThrough, [selected]: seq };
    setReadThrough(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Keep in-memory read state. */ }
  }, [selected, ready, seq, focused, readThrough]);
  return readThrough;
}
