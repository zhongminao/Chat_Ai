import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { WatchResource } from '../../api/types';

export function useWatch(sessionId: string | null, onChange: () => void) {
  const [resources, setResources] = useState<WatchResource[]>([]);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const changed = useRef(onChange); changed.current = onChange;
  useEffect(() => {
    const abort = new AbortController();
    setResources([]); setError(false);
    let timer: ReturnType<typeof setTimeout>;
    let delay = 1000;
    let cursor: number | undefined;
    const current = new Map<string, WatchResource>();
    async function poll() {
      try {
        while (!abort.signal.aborted) {
          const result = await api.watch(sessionId!, cursor, cursor === undefined ? 0 : 25, abort.signal);
          if (abort.signal.aborted) return;
          const snapshot = cursor === undefined;
          if (snapshot) current.clear();
          cursor = result.cursor;
          setError(false); delay = 1000;
          for (const resource of result.changes) {
            if (resource.deleted) current.delete(resource.id);
            else current.set(resource.id, resource);
          }
          if (snapshot || result.changes.length) {
            setResources([...current.values()]);
            changed.current();
          }
        }
      } catch {
        if (abort.signal.aborted) return;
        setError(true);
        // A restarted server may no longer recognize the previous cursor.
        cursor = undefined;
        timer = setTimeout(() => { void poll(); }, delay);
        delay = Math.min(delay * 2, 30000);
      }
    }
    if (sessionId) void poll();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [sessionId, attempt]);
  return { resources, error, retry: () => setAttempt(value => value + 1) };
}
