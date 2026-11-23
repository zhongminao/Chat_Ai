import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
import { ModelPicker } from './ModelPicker';

const state = vi.hoisted(() => ({ page: 'models' }));

vi.mock('react', async original => ({
  ...await original<typeof import('react')>(), useState: (initial: unknown) => [initial === null ? state.page : initial, vi.fn()],
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


it.each([ [[]], [['high']], [['low', 'high']] ])('only renders the effort page for multiple levels (%j)', (levels) => {
  state.page = 'effort';
  try {
    const html = renderToStaticMarkup(<ModelPicker {...props} model={{ provider: 'gpt', name: 'sol' }} groups={[
      { provider: 'gpt', displayName: 'GPT', models: [{ id: 'sol', name: 'Sol', enabled: true, reasoning_efforts: levels }] },
    ]} />);
    expect(html.includes('type="range"')).toBe(levels.length > 1);
    expect(html.includes('model-option selected')).toBe(levels.length < 2);
  } finally { state.page = 'models'; }
});


it('shows the active, remembered, or default level without a generic label', () => {
  vi.stubGlobal('localStorage', { getItem: (key: string) => key.includes('remembered') ? 'xhigh' : null });
  try {
    const html = renderToStaticMarkup(<ModelPicker {...props} model={{ provider: 'gpt', name: 'selected', reasoning_effort: 'low' }}
      groups={[{ provider: 'gpt', displayName: 'GPT', models: [
        { id: 'selected', name: 'Selected GPT', enabled: true, reasoning_efforts: ['low', 'high'], default_reasoning_effort: 'high' },
        { id: 'remembered', name: 'Remembered GPT', enabled: true, reasoning_efforts: ['high', 'xhigh'], default_reasoning_effort: 'high' },
        { id: 'default', name: 'Default GPT', enabled: true, reasoning_efforts: ['low', 'medium'], default_reasoning_effort: 'medium' },
        { id: 'fixed', name: 'Fixed GPT', enabled: true, reasoning_efforts: ['high'], default_reasoning_effort: 'high' },
        { id: 'offline', name: 'Offline GPT', enabled: false, reasoning_efforts: ['low', 'high'], default_reasoning_effort: 'high' },
      ] }]} />);
    expect(html).toContain('Selected GPT</span><span>低 ✓</span>');
    expect(html).toContain('Remembered GPT</span><span>最高</span>');
    expect(html).toContain('Default GPT</span><span>中</span>');
    expect(html).toContain('Fixed GPT</span><span></span>');
    expect(html).toContain('Offline GPT</span><span>不可用</span>');
    expect(html).not.toMatch(/[档挡]位/);
  } finally { vi.unstubAllGlobals(); }
});
