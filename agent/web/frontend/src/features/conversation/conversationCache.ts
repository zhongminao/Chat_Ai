import type { Conversation } from '../../state/conversation';

// A bounded, tab-local view cache. Only the JSONL journal is authoritative.
export class ConversationCache {
  private views = new Map<string, Conversation>();
  constructor(private limit = 5) {}

  get(id: string): Conversation | undefined {
    const view = this.views.get(id);
    if (view) { this.views.delete(id); this.views.set(id, view); }
    return view;
  }

  put(id: string, view: Conversation): void {
    this.views.delete(id);
    this.views.set(id, view);
    if (this.views.size > this.limit) this.views.delete(this.views.keys().next().value!);
  }

  delete(id: string): void { this.views.delete(id); }
}
