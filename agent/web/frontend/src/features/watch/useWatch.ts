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
    if (sessionId) void (async () => {
      let cursor: number | undefined;
      const current = new Map<string, WatchResource>();
      try {
        while (!abort.signal.aborted) {
          const result = await api.watch(sessionId, cursor, cursor === undefined ? 0 : 25, abort.signal);
          if (abort.signal.aborted) return;
          cursor = result.cursor;
          if (result.changes.length) {
            for (const resource of result.changes) {
              if (resource.deleted) current.delete(resource.id);
              else current.set(resource.id, resource);
            }
            setResources([...current.values()]);
            changed.current();
          }
        }
      } catch { if (!abort.signal.aborted) setError(true); }
    })();
    return () => abort.abort();
  }, [sessionId, attempt]);
  return { resources, error, retry: () => setAttempt(value => value + 1) };
}
