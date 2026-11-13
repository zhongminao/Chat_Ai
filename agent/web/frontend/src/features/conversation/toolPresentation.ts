import type { ToolItem } from '../../state/conversation';

// Presentation only: preserve protocol names in history, details and approvals.
const tools: Record<string, [string, string]> = {
  bash: ['Run command', 'command'],
  read_file: ['Read file', 'path'], write_file: ['Write file', 'path'],
  edit_file: ['Edit file', 'path'], read_image: ['View image', 'path'],
  search_resources: ['Search resources', 'query'],
  mcp_web_search: ['Search web', 'query'], mcp_web_fetch_url: ['Fetch page', 'url'],
};

export function toolPresentation(item: Pick<ToolItem, 'name' | 'arguments'>) {
  const mcp = item.name.startsWith('mcp_');
  const [label, field] = tools[item.name] ?? [item.name.replace(/^mcp_/, '').replaceAll('_', ' '), ''];
  const args = item.arguments && typeof item.arguments === 'object'
    ? item.arguments as Record<string, unknown> : {};
  return {
    label: `${mcp ? 'MCP · ' : ''}${label}`,
    target: typeof args[field] === 'string' ? args[field] as string : '',
    command: item.name === 'bash',
  };
}

export function toolFailed(item: ToolItem): boolean {
  const process = item.process;
  return item.status === 'interrupted' || item.status === 'rejected'
    || (typeof item.result === 'string' && /^\[(?:tool|mcp) error\]/.test(item.result))
    || Boolean(process && ((process.exitCode !== null && process.exitCode !== 0)
      || (process.reason !== 'running' && process.reason !== 'exited')));
}

export const processStatus = {
  running: '执行中', exited: '已退出', timeout: '超时', cancelled: '取消', error: '执行异常',
};

export const toolStatus = { running: '执行中', completed: '已完成', interrupted: '已中断', rejected: '已拒绝' };

export interface DisclosureState {
  isOpen: (id: string, fallback?: boolean) => boolean;
  toggle: (id: string, fallback?: boolean) => void;
}
