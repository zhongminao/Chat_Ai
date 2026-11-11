import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Composer } from './Composer';
import { writeTextDraft } from './textDraft';

afterEach(() => vi.unstubAllGlobals());

describe('composer draft restoration', () => {
  it('restores unsent text only for its session after switching back', () => {
    const store = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
      removeItem: (key: string) => { store.delete(key); },
    });
    writeTextDraft('draft-session', '未发送的内容');
    const render = (sessionId: string) => renderToStaticMarkup(<Composer busy={false} ready connected readOnly={false}
      status="connected" pending={null} accessMode="audit" accessDisabled={false} approvals={null}
      onAccessChange={() => {}} model={null} models={[]}
      modelsRefreshing={false} modelsError={null} onRefreshModels={async () => {}} sessionId={sessionId} images={[]}
      onUploaded={() => {}} onSend={async () => true}
      onGuide={async () => true} acceptedGuidance={[]} onStop={async () => true} onModelChange={async () => true} />);
    expect(render('draft-session')).toContain('未发送的内容</textarea>');
    expect(render('other-session')).not.toContain('未发送的内容');
    expect(render('draft-session')).toContain('未发送的内容</textarea>');
    writeTextDraft('draft-session', '');
  });
});

describe('attachment menu', () => {
  it('offers image, attachment and folder directly under the plus button', () => {
    const html = renderToStaticMarkup(<Composer busy={false} ready connected readOnly={false}
      status="connected" pending={null} accessMode="audit" accessDisabled={false} approvals={null}
      onAccessChange={() => {}} model={null} models={[]}
      modelsRefreshing={false} modelsError={null} onRefreshModels={async () => {}} sessionId="test" images={[]}
      onUploaded={() => {}} onSend={async () => true}
      onGuide={async () => true} acceptedGuidance={[]} onStop={async () => true} onModelChange={async () => true} />);
    expect(html).toContain('aria-label="添加内容"');
    expect(html).toContain('图片</button>');
    expect(html).toContain('附件</button>');
    expect(html).toContain('文件夹</button>');
    expect(html).not.toContain('attachment-submenu');
  });
});

describe('single composer action', () => {
  for (const busy of [false, true]) {
    it(busy ? 'has one enabled stop action while running with empty input' : 'has one disabled send action before any input', () => {
      const html = renderToStaticMarkup(<Composer busy={busy} ready connected readOnly={false}
        status="connected" pending={null} accessMode="audit" accessDisabled={false} approvals={null}
        onAccessChange={() => {}} model={null} models={[]}
        modelsRefreshing={false} modelsError={null} onRefreshModels={async () => {}} sessionId="test" images={[]}
        onUploaded={() => {}} onSend={async () => true}
        onGuide={async () => true} acceptedGuidance={[]} onStop={async () => true} onModelChange={async () => true} />);
      expect(html.match(/class="send-button /g)).toHaveLength(1);
      const action = html.match(/<button type="submit"[^>]*>/)?.[0] ?? '';
      expect(action).toContain(busy ? '停止执行' : '发送消息');
      expect(action.includes('disabled')).toBe(!busy);
    });
  }
});

describe('editing while reconnecting', () => {
  it('allows typing before the session is ready but does not send until readiness', () => {
    const html = renderToStaticMarkup(<Composer busy={false} ready={false} connected={false} readOnly={false}
      status="正在连接" pending={null} accessMode="audit" accessDisabled={false} approvals={null}
      onAccessChange={() => {}} model={null} models={[]}
      modelsRefreshing={false} modelsError={null} onRefreshModels={async () => {}} sessionId="pending-session" images={[]}
      onUploaded={() => {}} onSend={async () => true}
      onGuide={async () => true} acceptedGuidance={[]} onStop={async () => true} onModelChange={async () => true} />);
    expect(html).toMatch(/<textarea[^>]*aria-label="消息"[^>]*>/);
    expect(html.match(/<textarea[^>]*>/)?.[0]).not.toContain('disabled');
    expect(html).toContain('正在连接');
  });
});
