import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MessageList } from './MessageList';
import type { TextItem } from '../../state/conversation';

describe('guidance delivery position', () => {
  const render = (guidance: TextItem['guidance']) => renderToStaticMarkup(<MessageList
    items={[{ id: 'old', kind: 'text', role: 'assistant', content: 'original response' },
      { id: 'guide', kind: 'text', role: 'user', content: 'new direction', guidance }]}
    busy loading={false} assistantId="old" sessionId="test" images={[]} editingImage={false} onRenameImage={async () => true} />);

  it('keeps progress before a submitted but unapplied user message without badges', () => {
    const html = render('queued');
    expect(html.indexOf('run-indicator')).toBeLessThan(html.indexOf('new direction'));
    expect(html).not.toContain('guidance-status');
    expect(html).not.toContain('等待交付');
    expect(html.match(/run-indicator/g)).toHaveLength(1);
  });

  it('moves progress after the user message only after delivery', () => {
    const html = render('applied');
    expect(html.indexOf('run-indicator')).toBeGreaterThan(html.indexOf('new direction'));
  });

  it('renders an undelivered message as an ordinary user message', () => {
    const html = render('undelivered');
    expect(html).not.toContain('未送达');
    expect(html).toContain('class="message user"');
  });
});

describe('context feedback', () => {
  it('keeps existing messages visible while reconnecting and catching up', () => {
    const html = renderToStaticMarkup(<MessageList
      items={[{ id: 'old', kind: 'text', role: 'assistant', content: 'previously received text' }]}
      busy loading assistantId="old" sessionId="test" images={[]} editingImage={false} onRenameImage={async () => true} />);
    expect(html).toContain('previously received text');
    expect(html).not.toContain('加载会话');
    expect(html).toContain('aria-busy="true"');
  });

  it('renders progress and a quiet persistent completion marker', () => {
    for (const status of ['running', 'completed'] as const) {
      const html = renderToStaticMarkup(<MessageList items={[{ id: 'context:1', kind: 'context', status }]}
        busy={status === 'running'} loading={false} assistantId={null} sessionId="test" images={[]}
        editingImage={false} onRenameImage={async () => true} />);
      expect(html).toContain(status === 'running' ? '正在自动压缩上下文' : '上下文已自动压缩');
      expect(html).toContain('context-marker');
      expect(html).not.toContain('正在执行');
    }
  });
});
