"""Batch runtime inputs at safe boundaries; share the lock with submission."""
from ..agentsessionstate.input import UserInput
from ..agentsessionstate.message_updates import correction_message, mailbox_notice
from ..model.request_messages import build_user_message


class InputDelivery:
    def __init__(self, lock, emit, records, inbox=lambda: (), acknowledge=None):
        self.lock, self.emit = lock, emit
        self.inbox = inbox
        self.acknowledge = acknowledge
        corrections = [e for e in records if e['type'] == 'mailbox.correction']
        # The journal can commit before the request/ack. Replay its input, and
        # repair any missing acknowledgement at the next request.
        delivered = {e["messageId"] for e in corrections}
        self.correction_acks = []
        if delivered:
            self.correction_acks = [item["id"] for item in self.inbox()
                                    if item["id"] in delivered and not item.get("read_at")]
        self.latest_correction = corrections[-1]['content'] if corrections else None
        self.notified = {identifier for e in records if e["type"] == "mailbox.notified"
                         for identifier in e["messageIds"]}
        self.notified.update(delivered)
        # Accepted guidance survives cancellation and process recreation until a
        # model boundary consumes it. Explicitly undelivered historical guidance
        # is terminal and must not silently reappear.
        queued = {e['messageId']: e for e in records if e['type'] == 'guidance.queued'}
        finished = {e['messageId'] for e in records
                    if e['type'] in ('guidance.applied', 'guidance.undelivered')}
        self.pending: list[dict] = [
            {key: item[key] for key in ('messageId', 'content', 'images')}
            for identifier, item in queued.items() if identifier not in finished
        ]
        self.accepting = False
        self.received = {identifier: UserInput(item['content'], tuple(i['id'] for i in item.get('images', [])))
                         for identifier, item in queued.items()}

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

    def has_correction(self):
        return any(item.get('kind') == 'correction' and item['id'] not in self.notified for item in self.inbox())

    def acknowledge_corrections(self):
        with self.lock:
            identifiers = list(self.correction_acks)
        if self.acknowledge:
            for identifier in identifiers:
                self.acknowledge(identifier)
        with self.lock:
            self.correction_acks.clear()

    def take(self, run_id, *, finish=False):
        with self.lock:
            items = list(self.pending)
            for item in items:
                self.emit('guidance.applied', runId=run_id, **item)
                self.pending.remove(item)
            messages = [build_user_message(item['content'], [i['id'] for i in item['images']])
                        for item in items]
            identifiers = []
            for item in reversed(self.inbox()):
                identifier = item['id']
                if identifier in self.notified:
                    continue
                if item.get('kind') != 'correction':
                    identifiers.append(identifier)
                    continue
                self.emit('mailbox.correction', runId=run_id, messageId=identifier,
                          senderId=item['sender_id'], content=item['content'])
                self.notified.add(identifier)
                self.latest_correction = item['content']
                self.correction_acks.append(identifier)
                messages.append(correction_message(item['sender_id'], item['content']))
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
            # Closing a turn stops execution, not the user's already accepted
            # messages. A later turn delivers them before its first model call.
