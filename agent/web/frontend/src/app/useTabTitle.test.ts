import { afterEach, describe, expect, it, vi } from 'vitest';
import { getTabTitle, useTabTitle, type TabTitleState } from './useTabTitle';

vi.mock('react', () => ({ useEffect: (effect: () => void) => effect() }));
afterEach(() => vi.unstubAllGlobals());
const base: TabTitleState = {
  selected: 'session-1', title: '测试会话', loading: false, connected: true,
  ready: true, busy: false, sending: false, waitingApproval: false,
  error: null, history: [], live: [],
};

describe('browser tab title', () => {
  it('shows ready state and session name', () => {
    expect(getTabTitle(base)).toBe('○ 就绪 · 测试会话');
  });
  it.each([
    ['turn.completed', '✅ 已完成'], ['turn.failed', '❌ 失败'], ['turn.cancelled', '⏹ 已停止'],
  ] as const)('restores %s from history', (type, label) => {
    const event = type === 'turn.failed' ? { type, seq: 2, reason: 'test' } : { type, seq: 2 };
    expect(getTabTitle({ ...base, history: [event] })).toContain(label);
  });
  it('uses the latest turn across history and live events, ignoring metadata', () => {
    expect(getTabTitle({ ...base, history: [{ type: 'turn.failed', seq: 1, reason: 'old' }],
      live: [{ type: 'turn.completed', seq: 2 }, { type: 'model.completed', seq: 3 }] })).toContain('✅ 已完成');
  });
  it('does not carry an old outcome into a new run or another session', () => {
    const completed: TabTitleState = { ...base, history: [{ type: 'turn.completed', seq: 1 }] };
    expect(getTabTitle({ ...completed, busy: true })).toContain('⏳ 执行中');
    expect(getTabTitle({ ...completed, sending: true })).toContain('⏳ 执行中');
    expect(getTabTitle({ ...completed, live: [{ type: 'turn.started', seq: 2, prompt: 'next' }] })).not.toContain('已完成');
    expect(getTabTitle({ ...base, title: '另一个会话' })).toBe('○ 就绪 · 另一个会话');
  });
  it('prioritizes approvals and connection state over execution', () => {
    expect(getTabTitle({ ...base, busy: true, waitingApproval: true })).toContain('🔔 等待审批');
    expect(getTabTitle({ ...base, busy: true, connected: false })).toContain('⚠ 连接中 / 已断开');
    expect(getTabTitle({ ...base, ready: false })).toContain('正在恢复');
    expect(getTabTitle({ ...base, error: 'failed' })).toContain('❌ 出错');
  });
  it('handles initial loading and no selection', () => {
    expect(getTabTitle({ ...base, loading: true })).toContain('正在加载');
    expect(getTabTitle({ ...base, selected: null })).toBe('○ 未选择会话');
  });
  it('updates document.title', () => {
    vi.stubGlobal('document', { title: 'old' });
    useTabTitle(base);
    expect(document.title).toBe(getTabTitle(base));
    useTabTitle({ ...base, live: [{ type: 'turn.completed', seq: 1 }] });
    expect(document.title).toBe('✅ 已完成 · 测试会话');
  });
});
