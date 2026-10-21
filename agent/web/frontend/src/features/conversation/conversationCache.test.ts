import { describe, expect, it } from 'vitest';
import { emptyConversation } from '../../state/conversation';
import { ConversationCache } from './conversationCache';

describe('tab-local conversation cache', () => {
  it('keeps recently visited views within a bounded LRU and separates session IDs', () => {
    const cache = new ConversationCache(2);
    const a = { ...emptyConversation(), seq: 1 };
    const b = { ...emptyConversation(), seq: 2 };
    cache.put('a', a); cache.put('b', b);
    expect(cache.get('a')).toBe(a);
    cache.put('c', { ...emptyConversation(), seq: 3 });
    expect(cache.get('b')).toBeUndefined();
    expect(cache.get('a')?.seq).toBe(1);
    cache.delete('a');
    expect(cache.get('a')).toBeUndefined();
  });
});
