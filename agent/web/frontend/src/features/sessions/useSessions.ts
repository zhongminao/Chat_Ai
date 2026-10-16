import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { ModelGroup, SessionSummary } from '../../api/types';
import { errorMessage } from '../conversation/useConversation';

export async function findOrCreateEmptySession(sessions: SessionSummary[], preferred?: string | null): Promise<string> {
  const candidates = sessions
    .filter(session => !session.parent_session_id && session.empty && !session.busy)
    .sort((a, b) => Number(b.id === preferred) - Number(a.id === preferred));
  for (const candidate of candidates) {
    try {
      const snapshot = await api.snapshot(candidate.id);
      if (!snapshot.busy && snapshot.messages?.length === 0) return candidate.id;
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }
  return (await api.createSession()).id;
}

const emptySummary = (id: string): SessionSummary => ({
  id, title: '新会话', empty: true, busy: false, createdAt: null, updatedAt: Date.now() / 1000,
});

export function useSessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [models, setModels] = useState<ModelGroup[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const listVersion = useRef(0);
  const creatingRef = useRef(false);
  const renamingRef = useRef(false);

  const refresh = useCallback(async () => {
    const version = ++listVersion.current;
    try {
      const data = await api.sessions();
      if (version === listVersion.current) setSessions(data.sessions);
    } catch (error) { if (version === listVersion.current) setError(errorMessage(error)); }
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    setLoading(true); setError(null);
    Promise.all([api.sessions(abort.signal), api.models(abort.signal)]).then(async ([list, catalog]) => {
      if (!active) return;
      setModels(catalog.models); setSessions(list.sessions);
      const id = await findOrCreateEmptySession(list.sessions);
      if (!active) return;
      setSessions(items => items.some(item => item.id === id) ? items : [emptySummary(id), ...items]);
      setSelected(id);
      void refresh();
    }).catch(error => { if (active && !abort.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; abort.abort(); };
  }, [attempt, refresh]);

  async function create() {
    if (creatingRef.current) return;
    creatingRef.current = true; setCreating(true); setError(null);
    try {
      const id = await findOrCreateEmptySession(sessions, selected);
      // Show the selected empty session immediately; list refresh is not on this path.
      ++listVersion.current;
      setSessions(items => items.some(item => item.id === id) ? items : [emptySummary(id), ...items]);
      setSelected(id);
      void refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { creatingRef.current = false; setCreating(false); }
  }

  async function remove(id: string) {
    if (deleting || renamingRef.current || !window.confirm('删除这个历史会话？此操作无法撤销。')) return;
    setDeleting(id); setError(null);
    try {
      await api.deleteSession(id);
      if (id === selected) {
        const remaining = sessions.filter(item => item.id !== id);
        setSelected(remaining[0]?.id ?? null);
        if (!remaining.length) await create();
      }
      await refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { setDeleting(null); }
  }

  async function rename(id: string, title: string): Promise<boolean> {
    if (renamingRef.current || deleting) return false;
    renamingRef.current = true; setRenaming(id); setError(null);
    try {
      const renamed = await api.renameSession(id, title);
      ++listVersion.current;
      setSessions(items => items.map(item => item.id === id ? { ...item, title: renamed.title } : item));
      await refresh();
      return true;
    } catch (error) { setError(errorMessage(error)); return false; }
    finally { renamingRef.current = false; setRenaming(null); }
  }

  return { sessions, models, selected, select: setSelected, loading, creating, deleting, renaming, rename,
    error, clearError: () => setError(null), create, remove, refresh,
    retry: () => setAttempt(value => value + 1) };
}
