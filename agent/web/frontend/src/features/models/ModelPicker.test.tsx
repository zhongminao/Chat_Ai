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
    expect(html).toContain('暂无可用模型');
  });

  it('keeps existing models visible while refresh is running', () => {
    const html = renderToStaticMarkup(<ModelPicker {...props} refreshing groups={[
      { provider: 'local', displayName: 'Local', models: [{ id: 'qwen', name: 'Qwen', enabled: true }] },
    ]} />);
    expect(html).toContain('Qwen');
    expect(html).toContain('aria-busy="true"');
    expect(html).toMatch(/disabled="" aria-label="正在刷新模型列表"/);
  });

  it('shows an error and leaves a retry action', () => {
    const html = renderToStaticMarkup(<ModelPicker {...props} error="network error" />);
    expect(html).toContain('role="alert"');
    expect(html).toContain('network error');
    expect(html).toContain('aria-label="刷新模型列表"');
  });
});
