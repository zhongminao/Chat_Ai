"""SSE initialization, bounded history replay and live session events."""
import asyncio
import json
import queue

from ..core.session_runtime import SessionRuntime
from ..model.catalog import ModelCatalog


def initialize(runtime: SessionRuntime, after: int) -> tuple[dict, list[dict]]:
    with runtime.lock:
        records = runtime.session.events.read()
        sequence = records[-1]['seq'] if records else 0
        reset = after > sequence
        cursor = 0 if reset else after
        model = next((event['new'] for event in reversed(records) if event['type'] == 'model.changed'), None)
        model = model or runtime.meta.get('model') or ModelCatalog(runtime.registry.config.providers_file).default().as_dict()
        last_turn = next((event['type'] for event in reversed(records)
                          if event['type'] in {'turn.started', 'turn.completed', 'turn.cancelled', 'turn.failed'}), None)
        state = {'type': 'session.init', 'id': runtime.session.id, 'seq': sequence, 'after': cursor,
                 'reset': reset, 'busy': runtime.busy and last_turn not in {'turn.completed', 'turn.cancelled', 'turn.failed'},
                 'model': model, 'parent_session_id': runtime.parent_session_id,
                 'images': runtime.session.images.list()}
    return state, [event for event in records if event['seq'] > cursor]


def encode(data: dict, sequence: int | None = None) -> str:
    prefix = f'id: {sequence}\n' if sequence is not None else ''
    return prefix + 'data: ' + json.dumps(data, ensure_ascii=False) + '\n\n'


async def session_events(runtime: SessionRuntime, request, after: int):
    # Subscribe before reading SQLite so writes during initialization enter the queue.
    channel = runtime.bus.subscribe()
    try:
        state, records = await asyncio.to_thread(initialize, runtime, after)
        cursor = state['after']
        yield encode(state, cursor)  # Never acknowledge the replay boundary before its events.
        for event in records:
            cursor = event['seq']
            yield encode(event, cursor)
        yield encode({'type': 'session.ready', 'seq': state['seq']})
        ticks = 0
        while not await request.is_disconnected():
            try:
                event = channel.get_nowait()
            except queue.Empty:
                await asyncio.sleep(.1)
                ticks += 1
                if ticks >= 150:
                    yield ': heartbeat\n\n'
                    ticks = 0
                continue
            if event['seq'] <= cursor:
                continue
            # Recover a gap before advancing, including commits published out of order.
            pending = ([event] if event['seq'] == cursor + 1
                       else await asyncio.to_thread(runtime.session.events.read, cursor))
            for item in pending:
                cursor = item['seq']
                yield encode(item, cursor)
    finally:
        runtime.bus.unsubscribe(channel)
