import { useEffect, useReducer, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { HistoryPage, ImageAsset } from '../../api/types';
import { subscribe } from '../../api/events';
import { ConversationCache } from './conversationCache';
import { conversationReducer, emptyConversation, type Conversation, type Action } from '../../state/conversation';

export const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);

export function useConversation(id: string | null, onSessionsChanged: () => void) {
  const [, dispatch] = useReducer(conversationReducer, undefined, emptyConversation);
  const cache = useRef(new ConversationCache());
  const active = useRef<{ id: string; view: Conversation } | null>(null);
  // Mirror reducer actions for immediately switching tabs after an SSE batch.
  const displayed = active.current?.id === id ? active.current.view
    : id ? cache.current.get(id) ?? emptyConversation() : emptyConversation();
  const sendAction = (action: Action) => {
    if (active.current) active.current.view = conversationReducer(active.current.view, action);
    dispatch(action);
  };
  const [connected, setConnected] = useState(false);
  const [stopRequested, setStopRequested] = useState(false);
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const historyRef = useRef<{ id: string; page: HistoryPage } | null>(null);
  const morePending = useRef(false);
  const moreController = useRef<AbortController | null>(null);
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const [streamFailed, setStreamFailed] = useState(false);
  const [pending, setPending] = useState<'send' | 'guide' | 'stop' | 'model' | 'image' | null>(null);
  const generation = useRef(0);
  const commandPending = useRef(false);
  const renameBarrier = useRef<Promise<boolean>>(Promise.resolve(true));
  const changed = useRef(onSessionsChanged);
  changed.current = onSessionsChanged;

  useEffect(() => {
    const version = ++generation.current;
    const current = () => version === generation.current;
    const cached = id ? cache.current.get(id) : undefined;
    active.current = id ? { id, view: cached ?? emptyConversation() } : null;
    if (id) cache.current.delete(id);
    sendAction(cached && cached.history.length ? { type: 'restore', view: cached } : { type: 'reset' });
    setLoadedId(null); setConnected(false); setPending(null); setStopRequested(false); commandPending.current = false;
    renameBarrier.current = Promise.resolve(true);
    let replayThrough = 0;
    const controller = new AbortController();
    let close: (() => void) | undefined;
    historyRef.current = null;
    morePending.current = false;
    setLoadingMore(false); setHistoryError(null); setStreamFailed(false);
    if (id && cached && cached.history.length) {
      historyRef.current = { id, page: { events: [], snapshot_seq: cached.snapshotSeq,
        min_seq: cached.minSeq, has_more: cached.hasMore } };
      setLoadedId(id);
      connect(cached.seq);
    } else if (id) void api.history(id, controller.signal).then(page => {
      if (!current()) return;
      historyRef.current = { id, page };
      replayThrough = page.snapshot_seq;
      sendAction({ type: 'history', page });
      setLoadedId(id);
      connect(page.snapshot_seq);
    }).catch(error => {
      if (current() && !controller.signal.aborted) { setHistoryError(errorMessage(error)); sendAction({ type: 'error', error: errorMessage(error) }); }
    });
    function connect(after: number) {
      if (!id) return;
      close = subscribe(id, {
        initialize: session => {
          if (!current()) return;
          replayThrough = session.seq;
          if (session.reset) {
            cache.current.delete(id);
            active.current = { id, view: emptyConversation() };
            close?.();
            setConnected(false); setLoadedId(null);
            // A replaced journal needs a fresh bounded HTTP snapshot.
            setHistoryAttempt(value => value + 1);
            return;
          }
          sendAction({ type: 'initialize', session }); setLoadedId(id);
          if (!session.busy) setStopRequested(false);
        },
        ready: seq => {
          if (!current()) return;
          sendAction({ type: 'ready', seq }); changed.current();
        },
        connection: value => {
          if (!current()) return;
          setConnected(value);
          if (!value) sendAction({ type: 'disconnected' });
        },
        error: error => { if (current()) { setStreamFailed(true); setConnected(false); sendAction({ type: 'disconnected' }); sendAction({ type: 'error', error }); } },
        events: events => {
          if (!current()) return;
          sendAction({ type: 'events', events });
          if (events.some(event => event.seq > replayThrough &&
            ['turn.completed', 'turn.cancelled', 'turn.failed'].includes(event.type))) setStopRequested(false);
          if (events.some(event => event.seq > replayThrough &&
            ['turn.started', 'turn.completed', 'turn.cancelled', 'turn.failed', 'agent.created'].includes(event.type))) changed.current();
        },
      }, after);
    }
    return () => {
      ++generation.current;
      if (id && active.current?.id === id && active.current.view.history.length) cache.current.put(id, active.current.view);
      controller.abort(); moreController.current?.abort(); close?.();
    };
  }, [id, historyAttempt]);

  async function loadMore() {
    const loaded = historyRef.current;
    if (!id || loaded?.id !== id || !loaded.page.has_more || morePending.current) return;
    const version = generation.current;
    morePending.current = true;
    setLoadingMore(true); setHistoryError(null);
    const controller = new AbortController();
    moreController.current = controller;
    try {
      const page = await api.history(id, controller.signal, loaded.page.min_seq, loaded.page.snapshot_seq);
      if (version !== generation.current || historyRef.current !== loaded) return;
      if (page.snapshot_seq !== loaded.page.snapshot_seq ||
          page.events.at(-1)?.seq !== loaded.page.min_seq - 1 || page.min_seq >= loaded.page.min_seq) {
        throw new Error('历史分页边界不连续，请重试');
      }
      historyRef.current = { id, page };
      sendAction({ type: 'history', page, older: true });
    } catch (error) {
      if (version === generation.current && !controller.signal.aborted) setHistoryError(errorMessage(error));
    } finally {
      if (moreController.current === controller) moreController.current = null;
      if (version === generation.current) { morePending.current = false; setLoadingMore(false); }
    }
  }

  async function command(kind: 'send' | 'guide' | 'stop' | 'model' | 'image', operation: (session: string) => Promise<unknown>): Promise<boolean> {
    if (!id || commandPending.current) return false;
    const version = generation.current;
    commandPending.current = true;
    setPending(kind); sendAction({ type: 'error', error: null });
    if (kind === 'send') { setStopRequested(false); sendAction({ type: 'busy', busy: true }); }
    if (kind === 'stop') setStopRequested(true);
    try {
      await operation(id);
      return version === generation.current;
    } catch (error) {
      if (version === generation.current) {
        if (kind === 'send') sendAction({ type: 'busy', busy: false });
        if (kind === 'stop') setStopRequested(false);
        sendAction({ type: 'error', error: errorMessage(error) });
      }
      return false;
    } finally {
      if (version === generation.current) { commandPending.current = false; setPending(null); }
    }
  }

  function renameImage(image: string, name: string) {
    const operation = command('image', async session => {
      const version = generation.current;
      const result = await api.renameImage(session, image, name);
      if (version === generation.current) sendAction({ type: 'image', image: result.image });
    });
    renameBarrier.current = operation;
    return operation;
  }

  async function sendMessage(content: string, images: string[] = []) {
    const version = generation.current;
    const barrier = renameBarrier.current;
    const saved = await barrier;
    if (barrier === renameBarrier.current) renameBarrier.current = Promise.resolve(true);
    if (!saved || version !== generation.current) return false;
    return command('send', session => api.send(session, content, images));
  }

  return {
    ...displayed,
    loadMore, loadingMore, historyError, retryHistory: () => setHistoryAttempt(value => value + 1),
    ready: displayed.ready && loadedId === id && !streamFailed,
    connected: connected && loadedId === id && !streamFailed,
    pending: pending ?? (displayed.busy && stopRequested ? 'stop' : null),
    send: sendMessage,
    guide: (messageId: string, text: string, images: string[]) => command('guide', session => api.guide(session, messageId, text, images)),
    registerImage: (image: ImageAsset) => sendAction({ type: 'image', image }),
    renameImage,
    stop: () => command('stop', session => api.stop(session)),
    switchModel: (provider: string, model: string) => command('model', async session => {
      const version = generation.current;
      const result = await api.switchModel(session, provider, model);
      if (version === generation.current) sendAction({ type: 'model', model: result.model });
    }),
  };
}
