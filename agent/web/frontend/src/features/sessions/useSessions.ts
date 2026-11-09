import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { Model, ModelGroup, SessionSummary } from '../../api/types';
import { errorMessage } from '../conversation/useConversation';

const selectionKey = 'chat-ai:selected-session';

export function restoreSession(sessions: SessionSummary[]): string | null {
  try {
    const saved = sessionStorage.getItem(selectionKey);
    return saved && sessions.some(session => session.id === saved && !session.empty) ? saved : null;
  } catch { return null; }
}

export function useSessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [models, setModels] = useState<ModelGroup[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [updating, setUpdating] = useState<string | null>(null);
  const updatingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const listVersion = useRef(0);
  const [modelsRefreshing, setModelsRefreshing] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const modelRequest = useRef<AbortController | null>(null);
  const [defaultModel, setDefaultModel] = useState<Model | null>(null);

  const refreshModels = useCallback(async () => {
    if (modelRequest.current) return;
    const request = new AbortController();
    modelRequest.current = request;
    setModelsRefreshing(true); setModelsError(null);
    try {
      const catalog = await api.models(request.signal);
      if (!request.signal.aborted) { setModels(catalog.models); setDefaultModel(catalog.defaultModel); }
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

  // Refresh summaries for every session, not just the currently subscribed conversation.
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      await refresh();
      if (active) timer = setTimeout(() => { void poll(); }, 5000);
    };
    timer = setTimeout(() => { void poll(); }, 5000);
    return () => { active = false; clearTimeout(timer); };
  }, [refresh]);

  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    setLoading(true); setError(null);
    api.sessions(abort.signal).then(list => {
      if (!active) return;
      setSessions(list.sessions);
      select(restoreSession(list.sessions));
    }).catch(error => { if (active && !abort.signal.aborted) setError(errorMessage(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; abort.abort(); };
  }, [attempt, select]);

  async function remove(id: string) {
    if (deleting || updatingRef.current || !window.confirm(
      '删除这个会话及其所有子会话？聊天记录、图片和报告将一并删除，无法恢复。若主会话或子任务正在运行，请先停止。')) return;
    setDeleting(id); setError(null);
    try {
      await api.deleteSession(id);
      const remaining = sessions.filter(item => item.id !== id && item.parent_session_id !== id);
      ++listVersion.current;
      setSessions(remaining);
      if (id === selected || sessions.find(item => item.id === selected)?.parent_session_id === id) {
        select(null);
      }
      await refresh();
    } catch (error) { setError(errorMessage(error)); }
    finally { setDeleting(null); }
  }

  async function update(id: string, changes: { title?: string; pinned?: boolean; archived?: boolean }): Promise<boolean> {
    if (updatingRef.current || deleting) return false;
    updatingRef.current = true; setUpdating(id); setError(null);
    try {
      const saved = await api.updateSession(id, changes);
      ++listVersion.current;
      setSessions(items => items.map(item => item.id === id ? { ...item, ...saved } : item));
      await refresh();
      return true;
    } catch (error) { setError(errorMessage(error)); return false; }
    finally { updatingRef.current = false; setUpdating(null); }
  }

  return { updating, update, sessions, models, defaultModel, modelsRefreshing, modelsError, refreshModels, selected, select, loading, deleting,
    error, clearError: () => setError(null), remove, refresh,
    retry: () => setAttempt(value => value + 1) };
}
