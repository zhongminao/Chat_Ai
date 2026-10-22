import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { SessionRow } from './SessionRow';
import { SessionMenu } from './SessionMenu';

const hooks = vi.hoisted(() => ({ values: [] as unknown[], index: 0, saving: { current: false } }));
vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState(initial: unknown) {
    const index = hooks.index++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => { hooks.values[index] = value; }];
  },
  useRef: () => hooks.saving,
}));

const props = {
  session: { id: 'one', title: '原名称', createdAt: null, updatedAt: 0 },
  selected: false, busy: false, deleting: null, renaming: null, updating: null,
  onSelect: vi.fn(), onDelete: vi.fn(), onRename: vi.fn(), onUpdate: vi.fn(),
};
function render() { hooks.index = 0; return SessionRow(props); }
function form() {
  return render().props.children as ReactElement<{
    onBlur: (event: unknown) => void;
    onSubmit: (event: unknown) => void;
    children: ReactElement[];
  }>;
}
beforeEach(() => {
  vi.clearAllMocks(); hooks.values = [true, '新名称', false]; hooks.saving.current = false;
  props.onRename.mockResolvedValue(true);
});

describe('session row rename and actions', () => {
  it('saves when focus leaves the rename form', async () => {
    form().props.onBlur({ currentTarget: { contains: () => false }, relatedTarget: null });
    await Promise.resolve();
    expect(props.onRename).toHaveBeenCalledExactlyOnceWith('one', '新名称');
    expect(hooks.values[0]).toBe(false);
  });
  it('does not save when moving focus to save/cancel controls', () => {
    form().props.onBlur({ currentTarget: { contains: () => true }, relatedTarget: {} });
    expect(props.onRename).not.toHaveBeenCalled();
  });
  it('prevents duplicate Enter and blur saves', async () => {
    const element = form();
    element.props.onSubmit({ preventDefault() {} });
    element.props.onBlur({ currentTarget: { contains: () => false }, relatedTarget: null });
    await Promise.resolve();
    expect(props.onRename).toHaveBeenCalledOnce();
  });
  it('leaves edit mode without sending empty or unchanged names', () => {
    for (const title of ['  ', props.session.title]) {
      hooks.values = [true, title, false];
      form().props.onSubmit({ preventDefault() {} });
      expect(hooks.values[0]).toBe(false);
    }
    expect(props.onRename).not.toHaveBeenCalled();
  });
  it('preserves a failed draft for retry', async () => {
    props.onRename.mockResolvedValue(false);
    form().props.onSubmit({ preventDefault() {} });
    await Promise.resolve();
    expect(hooks.values).toEqual([true, '新名称', true]);
  });
  it('exposes a single more-actions trigger rather than old inline buttons', () => {
    hooks.values = [false, '', false];
    const fragment = render().props.children as ReactElement<{ children: ReactElement[] }>;
    const menu = fragment.props.children.find(child => child.type === SessionMenu)!;
    expect(menu).toBeDefined();
    const html = renderToStaticMarkup(<SessionRow {...props} session={{ ...props.session, pinned: true }} />);
    expect(html).not.toContain('已置顶');
    expect(html).not.toContain('session-pin');
    expect(html).toContain('会话操作');
    expect(html).not.toContain('<time');
    expect(html).not.toContain('修改会话名称：');
    expect(html).not.toContain('删除会话：');
  });
});
