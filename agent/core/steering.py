"""Immutable accepted guidance; the session lock also guards execution finalization."""
from ..workflow.input import UserInput


class SteeringQueue:
    def __init__(self, lock, emit, records):
        self.lock, self.emit = lock, emit
        self.pending: list[dict] = []
        self.accepting = False
        self.received = {e['messageId']: UserInput(e['content'], tuple(i['id'] for i in e.get('images', [])))
                         for e in records if e['type'] == 'guidance.queued'}

    def begin(self):
        with self.lock:
            self.accepting = True

    def add(self, identifier, value, assets):
        with self.lock:
            if identifier in self.received:
                if self.received[identifier] != value:
                    raise ValueError('此引导已发送，不能修改')
                return
            if not self.accepting:
                raise ValueError('当前执行已结束或正在停止')
            item = {'messageId': identifier, 'content': value.text, 'images': assets}
            self.emit('guidance.queued', **item)
            self.received[identifier] = value
            self.pending.append(item)

    def take(self, run_id, *, finish=False):
        with self.lock:
            items = list(self.pending)
            for item in items:
                self.emit('guidance.applied', runId=run_id, **item)
                self.pending.remove(item)
            if finish and not items:
                self.accepting = False
            return [self.received[item['messageId']] for item in items]

    def close(self):
        with self.lock:
            self.accepting = False
            for item in self.pending:
                self.emit('guidance.undelivered', messageId=item['messageId'])
            self.pending.clear()
