import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { AccessMode, ApprovalSnapshot } from '../../api/types';

export function useApprovals(id: string | null) {
  const [snapshot, setSnapshot] = useState<ApprovalSnapshot | null>(null);
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const generation = useRef(0);
  const commandPending = useRef(false);

  function apply(value: ApprovalSnapshot) {
    setSnapshot(previous => !previous || value.instanceId !== previous.instanceId || value.revision >= previous.revision ? value : previous);
  }

  useEffect(() => {
    const version = ++generation.current;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setSnapshot(null); setLoadedId(null); setError(null); setPending(false); commandPending.current = false;
    async function refresh() {
      try {
        const value = await api.approvals(id!, abort.signal);
        if (version === generation.current) { apply(value); setLoadedId(id); setError(null); }
      } catch (err) {
        if (!abort.signal.aborted && version === generation.current) setError(String(err));
      } finally {
        if (!abort.signal.aborted) timer = setTimeout(refresh, 1000);
      }
    }
    if (id) void refresh();
    return () => { ++generation.current; abort.abort(); clearTimeout(timer); };
  }, [id]);

  async function command(operation: () => Promise<unknown>) {
    if (!id || loadedId !== id || commandPending.current) return;
    const version = generation.current;
    commandPending.current = true; setPending(true); setError(null);
    try {
      const value = await operation();
      if (version === generation.current && value && typeof value === 'object' && 'revision' in value) apply(value as ApprovalSnapshot);
    } catch (err) {
      if (version === generation.current) setError(String(err));
    } finally {
      if (version === generation.current) { setPending(false); commandPending.current = false; }
    }
  }

  return {
    snapshot: loadedId === id ? snapshot : null, error, pending,
    setMode: (mode: AccessMode) => command(() => api.accessMode(id!, mode)),
    decide: (approval: string, approved: boolean) => command(() => api.decideApproval(id!, approval, approved)),
    stop: (session: string) => command(() => api.stop(session)),
  };
}
