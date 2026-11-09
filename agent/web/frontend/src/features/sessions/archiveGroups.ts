import type { SessionSummary } from '../../api/types';

const archiveDate = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
});

export function groupArchivedSessions(sessions: SessionSummary[]) {
  const groups = new Map<string, SessionSummary[]>();
  const sorted = [...sessions].sort((a, b) => (b.archivedAt ?? -Infinity) - (a.archivedAt ?? -Infinity));
  for (const session of sorted) {
    const date = session.archivedAt == null ? '归档时间未知' : archiveDate.format(new Date(session.archivedAt * 1000));
    const group = groups.get(date);
    if (group) group.push(session);
    else groups.set(date, [session]);
  }
  return Array.from(groups, ([date, items]) => ({ date, sessions: items }));
}
