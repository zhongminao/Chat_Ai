import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionMenu } from './SessionMenu';

vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState: () => [{ top: 8, left: 8 }, vi.fn()],
}));
vi.mock('react-dom', async original => ({
  ...await original<typeof import('react-dom')>(),
  createPortal: (children: unknown) => children,
}));
const props = {
  title: '会话', pinned: false, archived: false, disabled: false, deleteDisabled: false,
  onRename: vi.fn(), onPin: vi.fn(), onArchive: vi.fn(), onDelete: vi.fn(),
};
beforeEach(() => vi.stubGlobal('document', { body: {} }));
afterEach(() => vi.unstubAllGlobals());

describe('session menu archive actions', () => {
  it('hides pin actions for archived sessions including legacy pinned records', () => {
    for (const pinned of [false, true]) {
      const html = renderToStaticMarkup(<SessionMenu {...props} archived pinned={pinned} />);
      expect(html).not.toContain('置顶');
      for (const label of ['重命名', '取消归档', '删除']) expect(html).toContain(label);
      expect(html.match(/role="menuitem"/g)).toHaveLength(3);
    }
  });
  it('keeps pin and unpin actions in normal history', () => {
    expect(renderToStaticMarkup(<SessionMenu {...props} />)).toContain('置顶');
    expect(renderToStaticMarkup(<SessionMenu {...props} pinned />)).toContain('取消置顶');
  });
});
