import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Composer } from './Composer';

describe('single composer action', () => {
  for (const busy of [false, true]) {
    it(busy ? 'has one enabled stop action while running with empty input' : 'has one disabled send action before any input', () => {
      const html = renderToStaticMarkup(<Composer busy={busy} ready connected readOnly={false}
        status="connected" pending={null} accessMode="audit" accessDisabled={false} approvals={null}
        onAccessChange={() => {}} model={null} models={[]} sessionId="test" images={[]}
        onUploaded={() => {}} onSend={async () => true}
        onGuide={async () => true} acceptedGuidance={[]} onStop={async () => true} onModelChange={async () => true} />);
      expect(html.match(/class="send-button /g)).toHaveLength(1);
      const action = html.match(/<button type="submit"[^>]*>/)?.[0] ?? '';
      expect(action).toContain(busy ? '停止执行' : '发送消息');
      expect(action.includes('disabled')).toBe(!busy);
    });
  }
});
