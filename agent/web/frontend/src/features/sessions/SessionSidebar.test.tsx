import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionSidebar } from './SessionSidebar';

const state = vi.hoisted(() => ({ open: false, index: 0 }));
vi.mock('react', async original => ({ ...await original<typeof import('react')>(), useState: (initial: unknown) => [state.index++ === 0 ? state.open : initial, vi.fn()] }));
const session = (id: string, updatedAt = 0) => ({ id, title: `会话-${id}`, createdAt: null, updatedAt });
const props = {
  sessions: [session('normal', 100), { ...session('pinned', 1), pinned: true },
    { ...session('archived', 2), archived: true }, { ...session('child'), parent_session_id: 'normal' }],
  selected: null, loading: false, deleting: null, updating: null,
  open: true, busy: false, onUpdate: vi.fn(), onSelect: vi.fn(),
  onCreate: vi.fn(), onDelete: vi.fn(), onClose: vi.fn(),
};
beforeEach(() => { state.open = false; state.index = 0; });
describe('history and archive directory', () => {
  it('hides old empty sessions in history, pinned and archived sections without changing the source list', () => {
    state.open = true;
    const sessions = [...props.sessions, ...[
      { ...session('empty-history'), empty: true },
      { ...session('empty-pinned'), empty: true, pinned: true },
      { ...session('empty-archived'), empty: true, archived: true },
    ]];
    const html = renderToStaticMarkup(<SessionSidebar {...props} sessions={sessions} />);
    for (const id of ['empty-history', 'empty-pinned', 'empty-archived']) expect(html).not.toContain(`会话-${id}`);
    expect(html).toContain('会话-normal');
    expect(sessions).toHaveLength(props.sessions.length + 3);
  });
  it('separates pinned and history sections without row badges, and hides archived/child rows', () => {
    const html = renderToStaticMarkup(<SessionSidebar {...props} />);
    expect(html.indexOf('会话-pinned')).toBeLessThan(html.indexOf('会话-normal'));
    expect(html).not.toContain('已置顶');
    expect(html).toContain('aria-label="置顶会话列表"');
    expect(html).toContain('aria-label="历史会话列表"');
    expect(html.indexOf('会话-pinned')).toBeLessThan(html.indexOf('aria-label="历史会话"'));
    expect(html.indexOf('会话-normal')).toBeGreaterThan(html.indexOf('aria-label="历史会话列表"'));
    expect(html).not.toContain('会话-archived');
    expect(html).not.toContain('会话-child');
    expect(html).toContain('归档会话');
    expect(html).not.toContain('Agent workspace');
  });
  it('omits the pinned section when no sessions are pinned', () => {
    const html = renderToStaticMarkup(<SessionSidebar {...props} sessions={props.sessions.filter(session => !('pinned' in session))} />);
    expect(html).not.toContain('aria-label="置顶会话"');
    expect(html).toContain('aria-label="历史会话列表"');
  });
  it('shows archived rows only in the expanded bottom directory', () => {
    state.open = true;
    const html = renderToStaticMarkup(<SessionSidebar {...props} />);
    expect(html).toContain('aria-expanded="true"');
    expect(html.indexOf('会话-archived')).toBeGreaterThan(html.indexOf('id="archived-sessions"'));
    expect(html.match(/title="会话-archived"/g)).toHaveLength(1);
  });
});
