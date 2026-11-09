import { useEffect, useState } from 'react';
import type { SessionSummary } from '../../api/types';

type ReadState = Record<string, number>;

export function sessionIndicator(session: SessionSummary, readThrough = session.activitySeq ?? 0): 'running' | 'failed' | 'unread' | null {
  if (session.busy) return 'running';
  if ((session.activitySeq ?? 0) <= readThrough) return null;
  if (session.status === 'failed') return 'failed';
  return 'unread';
}

export function useSessionReadState(sessions: SessionSummary[], selected: string | null, ready: boolean, seq: number) {
  const [readThrough, setReadThrough] = useState<ReadState>({});
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
    setReadThrough(current => {
      const next: ReadState = {};
      for (const session of sessions) {
        // Existing content is the baseline when this page first sees a session.
        const baseline = current[session.id] ?? session.activitySeq ?? 0;
        next[session.id] = session.id === selected && ready && focused
          ? Math.max(baseline, seq) : baseline;
      }
      const unchanged = Object.keys(current).length === sessions.length &&
        sessions.every(session => next[session.id] === current[session.id]);
      return unchanged ? current : next;
    });
  }, [sessions, selected, ready, seq, focused]);
  return readThrough;
}
