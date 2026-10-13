import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { ModelGroup, SessionSummary } from '../../api/types';
import { errorMessage } from '../conversation/useConversation';

const savedSession = () => {
  try { return localStorage.getItem('chat.session'); } catch { return null; }
};

export function useSessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [models, setModels] = useState<ModelGroup[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const listVersion = useRef(0);
  const creatingRef = useRef(false);

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
      const saved = savedSession();
      let id = list.sessions.find(item => item.id === saved)?.id ?? list.sessions[0]?.id;
      // Do not create a session from a StrictMode effect that has already been cleaned up.
      if (!id) {
        id = (await api.createSession()).id;
        if (!active) return;
        await refresh();
      }
      if (active) setSelected(id);
    }).catch(error => { if (active && !abort.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; abort.abort(); };
  }, [attempt, refresh]);

  useEffect(() => {
    if (selected) { try { localStorage.setItem('chat.session', selected); } catch { /* Storage may be unavailable. */ } }
  }, [selected]);

  async function create() {
    if (creatingRef.current) return;
    creatingRef.current = true; setCreating(true); setError(null);
    try {
      const session = await api.createSession();
      setSelected(session.id);
      await refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { creatingRef.current = false; setCreating(false); }
  }

  async function remove(id: string) {
    if (deleting || !window.confirm('删除这个历史会话？此操作无法撤销。')) return;
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

  return { sessions, models, selected, select: setSelected, loading, creating, deleting,
    error, clearError: () => setError(null), create, remove, refresh,
    retry: () => setAttempt(value => value + 1) };
}
