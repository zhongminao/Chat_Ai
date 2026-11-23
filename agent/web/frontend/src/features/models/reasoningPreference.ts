import type { ModelGroup } from '../../api/types';

type ModelOption = ModelGroup['models'][number];
const key = (provider: string, name: string) => `chat-ai:reasoning:${JSON.stringify([provider, name])}`;

export function savedEffort(provider: string, model: ModelOption): string | undefined {
  try {
    const value = localStorage.getItem(key(provider, model.id));
    if (value && model.reasoning_efforts?.includes(value)) return value;
  } catch { /* Browser storage may be unavailable. */ }
}

export function saveEffort(provider: string, name: string, value: string) {
  try { localStorage.setItem(key(provider, name), value); } catch { /* Current session is still updated. */ }
}
