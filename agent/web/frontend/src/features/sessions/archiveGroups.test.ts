import { describe, expect, it } from 'vitest';
import type { SessionSummary } from '../../api/types';
import { groupArchivedSessions } from './archiveGroups';

const session = (id: string, archivedAt?: number | null): SessionSummary => ({
  id, title: id, createdAt: null, updatedAt: 0, archived: true, archivedAt,
});
const time = (value: string) => Date.parse(value) / 1000;

describe('archive date groups', () => {
  it('uses Shanghai midnight and orders dates and rows by archive time, not activity', () => {
    const sessions = [
      { ...session('before', time('2026-11-09T15:59:59Z')), updatedAt: 9999999999 },
      session('midnight', time('2026-11-09T16:00:00Z')),
      session('later', time('2026-11-09T17:00:00Z')),
      session('unknown'), session('null', null),
    ];
    const groups = groupArchivedSessions(sessions);
    expect(groups.map(group => [group.date, group.sessions.map(item => item.id)])).toEqual([
      ['2026-11-10', ['later', 'midnight']], ['2026-11-09', ['before']],
      ['归档时间未知', ['unknown', 'null']],
    ]);
    expect(sessions.map(item => item.id)).toEqual(['before', 'midnight', 'later', 'unknown', 'null']);
  });
  it('returns only populated dates and keeps the Unix epoch as a known time', () => {
    expect(groupArchivedSessions([])).toEqual([]);
    expect(groupArchivedSessions([session('epoch', 0)])[0].date).toBe('1970-01-01');
  });
});
