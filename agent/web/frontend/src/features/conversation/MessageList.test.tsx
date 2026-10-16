import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MessageList } from './MessageList';

describe('context feedback', () => {
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
