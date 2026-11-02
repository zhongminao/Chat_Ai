/** Unsent composer text is scoped to one session and one browser tab. */
const prefix = 'chat-ai:composer-draft:';
const fallback = new Map<string, string>();

export function readTextDraft(sessionId: string | null): string {
  if (!sessionId) return '';
  const key = prefix + sessionId;
  try {
    const stored = sessionStorage.getItem(key);
    if (stored !== null) return stored;
  } catch { /* Private mode / storage unavailable: keep drafts in memory. */ }
  return fallback.get(key) ?? '';
}

export function writeTextDraft(sessionId: string | null, text: string): void {
  if (!sessionId) return;
  const key = prefix + sessionId;
  if (text) fallback.set(key, text);
  else fallback.delete(key);
  try {
    if (text) sessionStorage.setItem(key, text);
    else sessionStorage.removeItem(key);
  } catch { /* Keep the in-memory copy if storage is unavailable. */ }
}

/** Do not erase text typed after an asynchronous send started. */
export function clearTextDraftIfUnchanged(sessionId: string | null, sent: string): boolean {
  if (readTextDraft(sessionId) !== sent) return false;
  writeTextDraft(sessionId, '');
  return true;
}
