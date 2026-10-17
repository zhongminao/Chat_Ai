import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ApprovalPanel } from './ApprovalPanel';

describe('approval review', () => {
  it('shows the complete exact operation, source and only one-call decisions', () => {
    const decide = vi.fn();
    const html = renderToStaticMarkup(<ApprovalPanel requests={[{
      id: 'approval', sessionId: 'child-123456', runId: 'run', callId: 'call', tool: 'write_file',
      arguments: { path: 'game.js', content: '<script>\nfull file content\n</script>' },
    }]} sessionId="main" disabled={false} onDecide={decide} onStop={vi.fn()} />);
    expect(html).toContain('child-12');
    expect(html).toContain('&lt;script&gt;\nfull file content\n&lt;/script&gt;');
    expect(html).toContain('批准本次');
    expect(html).toContain('拒绝本次');
    expect(html).toContain('停止此任务');
    expect(decide).not.toHaveBeenCalled();
  });
});
