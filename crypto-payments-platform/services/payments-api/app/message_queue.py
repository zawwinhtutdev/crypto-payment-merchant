"""
Minimal in-memory pub/sub, standing in for a real broker (Azure Service Bus /
Event Hubs / Kafka) that would sit between microservices in production.

Demonstrates the *pattern* used for the payments-api -> notification-service
hop: publish-and-forget from the API, asynchronous consumption by a
downstream service, decoupling the two so the payments API's response time
never depends on notification delivery.
"""
from __future__ import annotations

from collections import defaultdict
from queue import Queue
from typing import Callable, Dict, List


class InMemoryMessageBus:
    def __init__(self) -> None:
        self._topics: Dict[str, "Queue[dict]"] = defaultdict(Queue)

    def publish(self, topic: str, message: dict) -> None:
        self._topics[topic].put(message)

    def consume_all(self, topic: str) -> List[dict]:
        """Drain and return all currently queued messages (non-blocking)."""
        out = []
        q = self._topics[topic]
        while not q.empty():
            out.append(q.get_nowait())
        return out


# Shared bus instance for the demo (in production: a managed broker, not a
# process-local object — separate services can't share Python memory).
bus = InMemoryMessageBus()
TRANSFER_SETTLED_TOPIC = "transfer.settled"
