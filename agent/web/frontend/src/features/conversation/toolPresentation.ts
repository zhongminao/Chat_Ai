import type { IconName } from '../../ui/Icon';
import type { ToolItem } from '../../state/conversation';

// Presentation only: preserve protocol names in history, details and approvals.
const tools: Record<string, [string, string, IconName]> = {
  ask_user: ['向你提问', 'question', 'chat'],
  bash: ['Run command', 'command', 'terminal'],
  read_file: ['Read file', 'path', 'file'], write_file: ['Write file', 'path', 'file'],
  edit_file: ['Edit file', 'path', 'edit'], read_image: ['View image', 'path', 'image'],
  search_resources: ['Search resources', 'query', 'search'],
  mcp_web_search: ['Search web', 'query', 'search'], mcp_web_fetch_url: ['Fetch page', 'url', 'globe'],
};

export function toolPresentation(item: Pick<ToolItem, 'name' | 'arguments'>) {
  const mcp = item.name.startsWith('mcp_');
  const [label, field, icon] = tools[item.name] ?? [item.name.replace(/^mcp_/, '').replaceAll('_', ' '), '', 'tool'];
  const args = item.arguments && typeof item.arguments === 'object'
    ? item.arguments as Record<string, unknown> : {};
  return {
    icon,
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
