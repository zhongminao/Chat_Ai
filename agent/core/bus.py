import queue
from typing import Any


class EventBus:
    def __init__(self):
        self.subscribers: list[queue.Queue[dict[str, Any]]] = []

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        channel: queue.Queue[dict[str, Any]] = queue.Queue()
        self.subscribers.append(channel)
        return channel

    def unsubscribe(self, channel: queue.Queue[dict[str, Any]]) -> None:
        if channel in self.subscribers:
            self.subscribers.remove(channel)

    def publish(self, event: dict[str, Any]) -> None:
        for channel in list(self.subscribers):
            channel.put(event)
