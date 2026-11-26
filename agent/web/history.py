"""Bounded display-history pages over the authoritative event journal.

The first request captures an immutable high-water sequence. Earlier pages use
that same sequence and never include events written after it.
"""

PAGE_EVENTS = 1000
TERMINAL = {'turn.completed', 'turn.cancelled', 'turn.failed'}


def _start_of_interaction(records: list[dict], index: int) -> int:
    """Do not begin a page with the middle of a turn (including its compaction)."""
    for pos in range(index, -1, -1):
        if records[pos]['type'] == 'turn.started':
            return pos
        if records[pos]['type'] in TERMINAL:
            return pos + 1
    return 0


def display_event(event: dict) -> dict:
    # Preserve event sequence numbers; tool continuation data is not display history.
    if event['type'] == 'mailbox.correction':
        return {key: value for key, value in event.items() if key != 'content'}
    if event['type'] == 'tool_call.delta':
        return {key: value for key, value in event.items() if key != 'delta'}
    if event['type'] == 'tool.requested' and event.get('tool') == 'notify_agent':
        return {**event, 'arguments': {key: value for key, value in event['arguments'].items()
                                      if key != 'content'}}
    if event['type'] == 'tool.completed' and event.get('tool') in {'inspect_agent', 'read_agent_message'}:
        return {**event, 'result': '[private collaboration data]'}
    if event['type'] == 'reasoning.delta':
        return {key: value for key, value in event.items() if key != 'text'}
    if event['type'] == 'model.completed' and 'reasoning_content' in event:
        return {key: value for key, value in event.items() if key != 'reasoning_content'}
    if event['type'] == 'context.compacted' and 'messages' in event:
        return {key: value for key, value in event.items() if key != 'messages'}
    return event


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
        start = _start_of_interaction(older, max(0, len(older) - PAGE_EVENTS))
        page = older[start:]
    return {'events': [display_event(event) for event in page], 'snapshot_seq': snapshot,
            'min_seq': page[0]['seq'] if page else 0,
            'has_more': bool(page and page[0]['seq'] > 1)}
