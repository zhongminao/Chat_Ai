import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
import { ModelPicker } from './ModelPicker';

vi.mock('react', async original => ({
  ...await original<typeof import('react')>(), useState: () => [true, vi.fn()],
}));

const props: ComponentProps<typeof ModelPicker> = {
  groups: [], model: null, disabled: false, refreshing: false, error: null,
  onRefresh: async () => {}, onChange: async () => true,
};

describe('model list refresh display', () => {
  it('hides empty and fully disabled groups', () => {
    const html = renderToStaticMarkup(<ModelPicker {...props} groups={[
      { provider: 'empty', displayName: 'Empty provider', models: [] },
      { provider: 'off', displayName: 'Offline provider', models: [{ id: 'off', name: 'Off', enabled: false }] },
    ]} />);
    expect(html).not.toContain('Empty provider');
    expect(html).not.toContain('Offline provider');
    expect(html).toContain('title="无可用模型"');
    expect(html).toContain('<span>无可用模型</span>');
    expect(html).toContain('role="status">无可用模型</div>');
    expect(html).toContain('aria-label="刷新模型列表"');
  });

  it.each([null, { provider: 'local', name: 'previous-model' }])('does not show a default or stale model for an empty list (model: %j)', model => {
    const html = renderToStaticMarkup(<ModelPicker {...props} model={model} />);
    expect(html).toContain('title="无可用模型"');
    expect(html).toContain('<span>无可用模型</span>');
    expect(html).toContain('role="status">无可用模型</div>');
    expect(html).not.toContain('previous-model');
    expect(html).not.toContain('<span>选择模型</span>');
    expect(html).toContain('aria-label="刷新模型列表"');
  });

  it('does not show the previous model when all models are disabled', () => {
    const html = renderToStaticMarkup(<ModelPicker {...props} model={{ provider: 'local', name: 'qwen' }} groups={[
      { provider: 'local', displayName: 'Local', models: [{ id: 'qwen', name: 'Qwen', enabled: false }] },
    ]} />);
    expect(html).toContain('title="无可用模型"');
    expect(html).toContain('<span>无可用模型</span>');
    expect(html).not.toContain('Qwen');
    expect(html).not.toContain('qwen');
  });

  it.each([false, true])('preserves the current model name when models are available (refreshing: %s)', refreshing => {
    const html = renderToStaticMarkup(<ModelPicker {...props} refreshing={refreshing} model={{ provider: 'local', name: 'qwen' }} groups={[
      { provider: 'local', displayName: 'Local', models: [{ id: 'qwen', name: 'Qwen', enabled: true }] },
    ]} />);
    expect(html).toContain('title="Qwen"');
    expect(html).toContain('<span>Qwen</span>');
    expect(html).not.toContain('无可用模型');
    expect(html).not.toContain('model-refresh');
  });

  it('keeps existing models visible while refresh is running', () => {
    const html = renderToStaticMarkup(<ModelPicker {...props} refreshing groups={[
      { provider: 'local', displayName: 'Local', models: [{ id: 'qwen', name: 'Qwen', enabled: true }] },
    ]} />);
    expect(html).toContain('Qwen');
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain('model-refresh');
  });

  it.each([null, 'network error'])('hides refresh when models are available (error: %s)', error => {
    const html = renderToStaticMarkup(<ModelPicker {...props} error={error} groups={[
      { provider: 'local', displayName: 'Local', models: [{ id: 'qwen', name: 'Qwen', enabled: true }] },
    ]} />);
    expect(html).toContain('Qwen');
    expect(html).not.toContain('model-refresh');
    expect(html).not.toContain('请点击刷新重试');
  });

  it('shows a disabled refresh button while loading an empty list', () => {
    const html = renderToStaticMarkup(<ModelPicker {...props} refreshing model={{ provider: 'local', name: 'previous-model' }} />);
    expect(html).toContain('title="正在加载模型列表…"');
    expect(html).toContain('role="status">正在加载模型列表…</div>');
    expect(html).not.toContain('previous-model');
    expect(html).toMatch(/disabled="" aria-label="正在刷新模型列表"/);
  });

  it('shows an error and leaves a retry action', () => {
    const html = renderToStaticMarkup(<ModelPicker {...props} error="network error" />);
    expect(html).toContain('title="无可用模型"');
    expect(html).toContain('role="status">无可用模型</div>');
    expect(html).toContain('role="alert"');
    expect(html).toContain('network error');
    expect(html).toContain('aria-label="刷新模型列表"');
  });
});
