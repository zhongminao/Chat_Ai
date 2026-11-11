import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MessageList } from './MessageList';
import type { TextItem } from '../../state/conversation';

describe('guidance delivery position', () => {
  const render = (guidance: TextItem['guidance'], busy = true) => renderToStaticMarkup(<MessageList
    items={[{ id: 'old', kind: 'text', role: 'assistant', content: 'original response' },
      { id: 'guide', kind: 'text', role: 'user', content: 'new direction', guidance }]}
    busy={busy} loading={false} assistantId="old" sessionId="test" images={[]} />);

  it('keeps progress before queued guidance and labels it not yet seen by the assistant', () => {
    const html = render('queued');
    expect(html.indexOf('run-indicator')).toBeLessThan(html.indexOf('new direction'));
    expect(html).toContain('guidance-status queued');
    expect(html).toContain('等待交付助手');
    expect(html).toContain('助手尚未看到');
    expect(html.match(/run-indicator/g)).toHaveLength(1);
  });

  it('moves progress after the user message only after delivery', () => {
    const html = render('applied');
    expect(html.indexOf('run-indicator')).toBeGreaterThan(html.indexOf('new direction'));
    expect(html).toContain('已交付助手');
    expect(html).not.toContain('助手尚未看到');
  });

  it('explains how pending guidance continues after the turn stops without implying delivery', () => {
    const html = render('queued', false);
    expect(html).toContain('待下次执行交付');
    expect(html).toContain('助手尚未看到');
    expect(html).toContain('停止后可发送新消息继续');
    expect(html).not.toContain('已交付助手');
    expect(html).not.toContain('run-indicator');
  });

  it('does not add guidance status to normal user messages', () => {
    const html = render(undefined, false);
    expect(html).toContain('class="message user"');
    expect(html).not.toContain('guidance-status');
  });

  it('labels undelivered guidance as unseen and explains how to recover', () => {
    const html = render('undelivered');
    expect(html).toContain('guidance-status undelivered');
    expect(html).toContain('未送达助手');
    expect(html).toContain('助手没有看到');
    expect(html).toContain('在新消息中重新说明');
  });
});

describe('context feedback', () => {
  it('keeps existing messages visible while reconnecting and catching up', () => {
    const html = renderToStaticMarkup(<MessageList
      items={[{ id: 'old', kind: 'text', role: 'assistant', content: 'previously received text' }]}
      busy loading assistantId="old" sessionId="test" images={[]} />);
    expect(html).toContain('previously received text');
    expect(html).not.toContain('加载会话');
    expect(html).toContain('aria-busy="true"');
  });

  it('renders progress and a quiet persistent completion marker', () => {
    for (const status of ['running', 'completed'] as const) {
      const html = renderToStaticMarkup(<MessageList items={[{ id: 'context:1', kind: 'context', status }]}
        busy={status === 'running'} loading={false} assistantId={null} sessionId="test" images={[]}
        />);
      expect(html).toContain(status === 'running' ? '正在自动压缩上下文' : '上下文已自动压缩');
      expect(html).toContain('context-marker');
      expect(html).not.toContain('正在执行');
    }
  });
});

describe('tool expansion', () => {
  it('renders tool parameters and result underneath the clickable title in a details element', () => {
    const html = renderToStaticMarkup(<MessageList
      items={[{ id: 'tool:1', kind: 'tool', name: 'read_file', status: 'completed', arguments: { path: 'a' }, result: 'done' }]}
      busy={false} loading={false} assistantId={null} sessionId="test" images={[]} />);
    expect(html).toMatch(/<details class="tool-card"><summary[^>]*>/);
    expect(html).not.toContain('execution-steps');
    expect(html.indexOf('read_file')).toBeLessThan(html.indexOf('调用参数'));
    expect(html.indexOf('调用参数')).toBeLessThan(html.indexOf('工具结果'));
  });

  it('groups adjacent tools into collapsed execution steps with the latest status', () => {
    const html = renderToStaticMarkup(<MessageList
      items={[
        { id: 'tool:1', kind: 'tool', name: 'read_file', status: 'completed', arguments: { path: 'a' }, result: 'one' },
        { id: 'tool:2', kind: 'tool', name: 'edit_file', status: 'completed', arguments: { path: 'a' }, result: 'two' },
        { id: 'tool:3', kind: 'tool', name: 'run_bash', status: 'running', arguments: { command: 'npm test' } },
      ]}
      busy loading={false} assistantId={null} sessionId="test" images={[]} />);
    expect(html.match(/class="execution-steps"/g)).toHaveLength(1);
    expect(html.match(/class="tool-status-dot/g)).toHaveLength(3);
    expect(html).toContain('执行步骤 · 3 个工具');
    expect(html).toContain('run_bash · 执行中');
    expect(html).not.toMatch(/<details class="execution-steps" open/);
    expect(html.match(/class="tool-card"/g)).toHaveLength(3);
    expect(html).toContain('read_file');
    expect(html).toContain('edit_file');
    expect(html).toContain('run_bash');
  });

  it('starts a new execution step after non-tool content', () => {
    const html = renderToStaticMarkup(<MessageList
      items={[
        { id: 'tool:1', kind: 'tool', name: 'read_file', status: 'completed' },
        { id: 'assistant:1', kind: 'text', role: 'assistant', content: '继续处理' },
        { id: 'tool:2', kind: 'tool', name: 'run_bash', status: 'completed' },
      ]}
      busy={false} loading={false} assistantId={null} sessionId="test" images={[]} />);
    expect(html.match(/class="execution-steps"/g)).toBeNull();
    expect(html.match(/class="tool-card"/g)).toHaveLength(2);
  });
});


describe('execution feedback', () => {
  it('shows execution or approval text only while running', () => {
    for (const busy of [false, true]) {
      for (const waitingCallIds of [[], ['call-1']]) {
        const html = renderToStaticMarkup(<MessageList
          items={[{ id: 'user', kind: 'text', role: 'user', content: 'start' }]}
          busy={busy} loading={false} assistantId={null} sessionId="test" images={[]}
          waitingCallIds={waitingCallIds} />);
        expect(html.includes('run-indicator')).toBe(busy);
        if (busy) expect(html).toContain(waitingCallIds.length ? '等待审批…' : '正在执行…');
      }
    }
  });
});
