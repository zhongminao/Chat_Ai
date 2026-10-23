import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { ModelGroup, SessionSummary } from '../../api/types';
import { errorMessage } from '../conversation/useConversation';

const selectionKey = 'chat-ai:selected-session';

export async function restoreOrCreateSession(sessions: SessionSummary[]): Promise<string> {
  let saved: string | null = null;
  try { saved = sessionStorage.getItem(selectionKey); } catch { /* Storage may be unavailable. */ }
  return saved && sessions.some(session => session.id === saved) ? saved : findOrCreateEmptySession(sessions);
}

export async function findOrCreateEmptySession(sessions: SessionSummary[], preferred?: string | null): Promise<string> {
  const available = (session: SessionSummary) => !session.parent_session_id && session.empty && !session.busy && !session.archived;
  if (sessions.some(available)) {
    // Recheck stale candidates using summaries, without loading conversation bodies.
    const fresh = (await api.sessions()).sessions.filter(available);
    const candidate = fresh.find(session => session.id === preferred) ?? fresh[0];
    if (candidate) return candidate.id;
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
  const [updating, setUpdating] = useState<string | null>(null);
  const updatingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const listVersion = useRef(0);
  const creatingRef = useRef(false);
  const renamingRef = useRef(false);
  const [modelsRefreshing, setModelsRefreshing] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const modelRequest = useRef<AbortController | null>(null);

  const refreshModels = useCallback(async () => {
    if (modelRequest.current) return;
    const request = new AbortController();
    modelRequest.current = request;
    setModelsRefreshing(true); setModelsError(null);
    try {
      const catalog = await api.models(request.signal);
      if (!request.signal.aborted) setModels(catalog.models);
    } catch (error) {
      if (!request.signal.aborted) setModelsError(errorMessage(error));
    } finally {
      if (modelRequest.current === request) {
        modelRequest.current = null;
        setModelsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void refreshModels();
    return () => { modelRequest.current?.abort(); modelRequest.current = null; };
  }, [refreshModels]);

  const select = useCallback((id: string | null) => {
    setSelected(id);
    try {
      if (id) sessionStorage.setItem(selectionKey, id);
      else sessionStorage.removeItem(selectionKey);
    } catch { /* Storage may be unavailable. */ }
  }, []);

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
    api.sessions(abort.signal).then(async list => {
      if (!active) return;
      setSessions(list.sessions);
      const id = await restoreOrCreateSession(list.sessions);
      if (!active) return;
      setSessions(items => items.some(item => item.id === id) ? items : [emptySummary(id), ...items]);
      select(id);
      void refresh();
    }).catch(error => { if (active && !abort.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; abort.abort(); };
  }, [attempt, refresh, select]);

  async function create() {
    if (creatingRef.current) return;
    creatingRef.current = true; setCreating(true); setError(null);
    try {
      const id = await findOrCreateEmptySession(sessions, selected);
      // Show the selected empty session immediately; list refresh is not on this path.
      ++listVersion.current;
      setSessions(items => items.some(item => item.id === id) ? items : [emptySummary(id), ...items]);
      select(id);
      void refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { creatingRef.current = false; setCreating(false); }
  }

  async function remove(id: string) {
    if (deleting || renamingRef.current || updatingRef.current || !window.confirm(
      '删除这个会话及其所有子会话？聊天记录、图片和报告将一并删除，无法恢复。若主会话或子任务正在运行，请先停止。')) return;
    setDeleting(id); setError(null);
    try {
      await api.deleteSession(id);
      const remaining = sessions.filter(item => item.id !== id && item.parent_session_id !== id);
      ++listVersion.current;
      setSessions(remaining);
      if (id === selected || sessions.find(item => item.id === selected)?.parent_session_id === id) {
        select(null);
        const emptyId = await findOrCreateEmptySession(remaining);
        setSessions(items => items.some(item => item.id === emptyId) ? items : [emptySummary(emptyId), ...items]);
        select(emptyId);
      }
      await refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { setDeleting(null); }
  }

  async function rename(id: string, title: string): Promise<boolean> {
    if (renamingRef.current || deleting || updatingRef.current) return false;
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

  async function update(id: string, changes: { pinned?: boolean; archived?: boolean }): Promise<boolean> {
    if (updatingRef.current || renamingRef.current || deleting) return false;
    updatingRef.current = true; setUpdating(id); setError(null);
    try {
      await api.updateSession(id, changes);
      ++listVersion.current;
      setSessions(items => items.map(item => item.id === id ? { ...item, ...changes } : item));
      await refresh();
      return true;
    } catch (error) { setError(errorMessage(error)); return false; }
    finally { updatingRef.current = false; setUpdating(null); }
  }

  return { updating, update, sessions, models, modelsRefreshing, modelsError, refreshModels, selected, select, loading, creating, deleting, renaming, rename,
    error, clearError: () => setError(null), create, remove, refresh,
    retry: () => setAttempt(value => value + 1) };
}
