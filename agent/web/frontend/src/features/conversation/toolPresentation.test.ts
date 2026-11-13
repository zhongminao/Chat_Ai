import { describe, expect, it } from 'vitest';
import type { ToolItem } from '../../state/conversation';
import type { ToolProcess } from '../../api/types';
import { toolFailed, toolPresentation } from './toolPresentation';

const bash: ToolItem = { id: 'tool:bash', kind: 'tool', name: 'bash', status: 'completed', arguments: { command: 'echo hello\necho world' }, result: 'output' };
const process = (reason: ToolProcess['reason'], exitCode: number | null): ToolProcess => ({ pid: 10, pgid: 10, exitCode, reason });

describe('tool presentation', () => {
  it('preserves the complete multiline bash command', () => {
    expect(toolPresentation(bash)).toMatchObject({ command: true, target: 'echo hello\necho world' });
  });
  it('recognizes nonzero exit codes and exceptional reasons without error text', () => {
    expect(toolFailed({ ...bash, process: process('exited', 1) })).toBe(true);
    for (const reason of ['timeout', 'cancelled', 'error'] as const) {
      expect(toolFailed({ ...bash, status: 'running', process: process(reason, null) })).toBe(true);
    }
  });
  it('does not treat missing, null or zero exit codes as a failure', () => {
    expect(toolFailed(bash)).toBe(false);
    expect(toolFailed({ ...bash, process: process('running', null) })).toBe(false);
    expect(toolFailed({ ...bash, process: process('exited', 0) })).toBe(false);
    expect(toolFailed({ ...bash, process: process('exited', null) })).toBe(false);
  });
  it('keeps existing failure indicators for legacy records', () => {
    expect(toolFailed({ ...bash, result: '[tool error] failed' })).toBe(true);
    expect(toolFailed({ ...bash, result: '[mcp error] failed' })).toBe(true);
    expect(toolFailed({ ...bash, status: 'interrupted' })).toBe(true);
    expect(toolFailed({ ...bash, status: 'rejected' })).toBe(true);
  });
});
