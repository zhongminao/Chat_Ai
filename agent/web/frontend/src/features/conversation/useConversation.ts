import { useEffect, useReducer, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { ImageAsset } from '../../api/types';
import { subscribe } from '../../api/events';
import { conversationReducer, emptyConversation } from '../../state/conversation';

export const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);

export function useConversation(id: string | null, onTurnEnded: () => void) {
  const [state, dispatch] = useReducer(conversationReducer, undefined, emptyConversation);
  const [connected, setConnected] = useState(false);
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [pending, setPending] = useState<'send' | 'stop' | 'model' | 'image' | null>(null);
  const generation = useRef(0);
  const commandPending = useRef(false);
  const renameBarrier = useRef<Promise<boolean>>(Promise.resolve(true));
  const ended = useRef(onTurnEnded);
  ended.current = onTurnEnded;

  useEffect(() => {
    const version = ++generation.current;
    const abort = new AbortController();
    let close: (() => void) | undefined;
    const current = () => version === generation.current;
    dispatch({ type: 'reset' });
    setLoadedId(null); setConnected(false); setPending(null); commandPending.current = false;
    renameBarrier.current = Promise.resolve(true);
    if (id) {
      api.snapshot(id, abort.signal).then(snapshot => {
        if (!current()) return;
        dispatch({ type: 'snapshot', snapshot });
        setLoadedId(id);
        close = subscribe(id, {
          connection: value => { if (current()) setConnected(value); },
          error: error => { if (current()) dispatch({ type: 'error', error }); },
          events: events => {
            if (!current()) return;
            dispatch({ type: 'events', events });
            // Replaying historical events should not refresh the sidebar for every old turn.
            if (events.some(event => event.seq > snapshot.seq &&
              ['turn.completed', 'turn.cancelled', 'turn.failed'].includes(event.type))) ended.current();
          },
        });
      }).catch(error => {
        if (current() && !abort.signal.aborted) dispatch({ type: 'error', error: errorMessage(error) });
      });
    }
    return () => { ++generation.current; abort.abort(); close?.(); };
  }, [id]);

  async function command(kind: 'send' | 'stop' | 'model' | 'image', operation: (session: string) => Promise<unknown>): Promise<boolean> {
    if (!id || commandPending.current) return false;
    const version = generation.current;
    commandPending.current = true;
    setPending(kind); dispatch({ type: 'error', error: null });
    if (kind === 'send') dispatch({ type: 'busy', busy: true });
    try {
      await operation(id);
      return version === generation.current;
    } catch (error) {
      if (version === generation.current) {
        if (kind === 'send') dispatch({ type: 'busy', busy: false });
        dispatch({ type: 'error', error: errorMessage(error) });
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
      if (version === generation.current) dispatch({ type: 'image', image: result.image });
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
    ...state,
    ready: state.ready && loadedId === id,
    connected: connected && loadedId === id,
    pending,
    send: sendMessage,
    registerImage: (image: ImageAsset) => dispatch({ type: 'image', image }),
    renameImage,
    stop: () => command('stop', session => api.stop(session)),
    switchModel: (provider: string, model: string) => command('model', async session => {
      const version = generation.current;
      const result = await api.switchModel(session, provider, model);
      if (version === generation.current) dispatch({ type: 'model', model: result.model });
    }),
  };
}
