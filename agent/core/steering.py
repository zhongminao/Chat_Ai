"""Batch runtime inputs at safe boundaries; share the lock with submission."""
from ..workflow.input import UserInput
from ..workflow.message_updates import mailbox_notice
from ..model.request_messages import build_user_message


class InputDelivery:
    def __init__(self, lock, emit, records, inbox=lambda: ()):
        self.lock, self.emit = lock, emit
        self.inbox = inbox
        self.notified = {identifier for e in records if e["type"] == "mailbox.notified"
                         for identifier in e["messageIds"]}
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

    def has_pending(self):
        with self.lock:
            return bool(self.pending or any(item['id'] not in self.notified for item in self.inbox()))

    def take(self, run_id, *, finish=False):
        with self.lock:
            items = list(self.pending)
            for item in items:
                self.emit('guidance.applied', runId=run_id, **item)
                self.pending.remove(item)
            messages = [build_user_message(item['content'], [i['id'] for i in item['images']])
                        for item in items]
            # Mail stays durable in its own store. Only framework-owned IDs enter
            # system context; reading/acknowledging the body remains a tool call.
            identifiers = [item['id'] for item in reversed(self.inbox())
                           if item['id'] not in self.notified]
            if identifiers:
                self.emit('mailbox.notified', runId=run_id, messageIds=identifiers)
                self.notified.update(identifiers)
                messages.append(mailbox_notice(identifiers))
            if finish and not messages:
                self.accepting = False
            return messages

    def close(self):
        with self.lock:
            self.accepting = False
            for item in self.pending:
                self.emit('guidance.undelivered', messageId=item['messageId'])
            self.pending.clear()
