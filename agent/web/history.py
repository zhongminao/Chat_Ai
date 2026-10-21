"""Bounded display-history pages over the authoritative event journal.

The first request captures an immutable high-water sequence. Earlier pages use
that same sequence and never include events written after it.
"""

PAGE_EVENTS = 200
TERMINAL = {'turn.completed', 'turn.cancelled', 'turn.failed'}


def _start_of_interaction(records: list[dict], index: int) -> int:
    """Do not begin a page with the middle of a turn (including its compaction)."""
    for pos in range(index, -1, -1):
        if records[pos]['type'] == 'turn.started':
            return pos
        if records[pos]['type'] in TERMINAL:
            return pos + 1
    return 0


def history_page(log, *, before: int | None = None, through: int | None = None) -> dict:
    # EventLog.read currently validates/scans the complete JSONL; filter once
    # here, so every boundary and the snapshot high-water mark agree.
    records = log.read()
    latest = records[-1]['seq'] if records else 0
    if before is None:
        snapshot = latest
        if not records:
            return {'events': [], 'snapshot_seq': 0, 'min_seq': 0, 'has_more': False}
        start = _start_of_interaction(records, max(0, len(records) - PAGE_EVENTS))
        page = records[start:]
    else:
        if through is None or through < 0 or before < 1 or before > through or through > latest:
            raise ValueError('Invalid history cursor or snapshot')
        snapshot = through
        older = [event for event in records if event['seq'] < before and event['seq'] <= snapshot]
        if not older:
            return {'events': [], 'snapshot_seq': snapshot, 'min_seq': 0,
                    'has_more': False}
        # Find the nearest successful compaction before the current page.
        # Keep a compaction inside a turn together with that turn; a standalone
        # compaction belongs to the newer segment starting at that marker.
        boundary = 0
        for index in range(len(older) - 1, -1, -1):
            if older[index]['type'] != 'context.compacted':
                continue
            candidate = _start_of_interaction(older, index)
            if candidate > 0:
                boundary = candidate
                break
        page = older[boundary:]
    return {'events': page, 'snapshot_seq': snapshot,
            'min_seq': page[0]['seq'] if page else 0,
            'has_more': bool(page and page[0]['seq'] > 1)}
