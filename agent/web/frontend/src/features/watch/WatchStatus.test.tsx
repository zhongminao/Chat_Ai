import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, expect, it, vi } from 'vitest';
import { WatchStatus } from './WatchStatus';

const state = vi.hoisted(() => ({ resources: [] as Record<string, unknown>[], error: false, retry: vi.fn() }));
vi.mock('./useWatch', () => ({ useWatch: () => state }));
const render = () => renderToStaticMarkup(<WatchStatus sessionId="parent" onChange={() => {}} />);

beforeEach(() => { state.resources = []; state.error = false; });

it('counts only agents when mailbox resources are present', () => {
  state.resources = [
    { id: 'agent:1', kind: 'agent', status: 'completed' },
    { id: 'agent:2', kind: 'agent', status: 'failed' },
    { id: 'mailbox', kind: 'mailbox', unread_count: 1 },
  ];
  expect(render()).toContain('0 个运行中 · 2 个已结束');
  state.resources[0].status = 'running';
  expect(render()).toContain('1 个运行中 · 1 个已结束');
});

it('hides task counts when only the mailbox exists', () => {
  state.resources = [{ id: 'mailbox', kind: 'mailbox' }];
  expect(render()).toBe('');
});

it('keeps connection errors visible without agents', () => {
  state.error = true;
  expect(render()).toContain('后台状态连接中断');
});
