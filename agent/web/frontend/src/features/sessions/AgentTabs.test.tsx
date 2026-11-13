import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { SessionSummary } from '../../api/types';
import { AgentTabs } from './AgentTabs';

const root: SessionSummary = { id: 'root', title: 'Main', createdAt: '2026-01-01', updatedAt: 0 };
const child = (number: number): SessionSummary => ({ id: `c${number}`, title: `Task ${number}`,
  createdAt: `2026-01-${String(number + 1).padStart(2, '0')}`, updatedAt: 0, parent_session_id: root.id });
const render = (sessions: SessionSummary[], selected = root.id) =>
  renderToStaticMarkup(<AgentTabs sessions={sessions} selected={selected} onSelect={vi.fn()} />);

describe('subagent navigation', () => {
  it('orders newest first but keeps stable creation ordinals when selecting a child', () => {
    const sessions = [child(2), root, child(1), child(3)];
    const html = render(sessions);
    expect(html.indexOf('子助手 3')).toBeLessThan(html.indexOf('子助手 2'));
    expect(html.indexOf('子助手 2')).toBeLessThan(html.indexOf('子助手 1'));
    expect(html).not.toContain('agent-child-picker');
    expect(render(sessions, 'c2').indexOf('子助手 3')).toBeLessThan(render(sessions, 'c2').indexOf('子助手 2'));
    expect(sessions[0].id).toBe('c2'); // Sorting must not mutate caller-owned sessions.
  });

  it('collapses a long child list to a picker, newest task as the first option', () => {
    const sessions = [root, ...Array.from({ length: 9 }, (_, index) => child(index + 1))];
    const html = render(sessions, 'c4');
    expect(html).toContain('class="agent-children collapsed"');
    expect(html).toContain('aria-label="选择子助手"');
    expect(html).toContain('<select');
    expect(html.indexOf('value="c9"')).toBeLessThan(html.indexOf('value="c1"'));
    expect(html).toContain('value="c4" selected=""');
    expect(html).toContain('子助手（9）');
  });
});
