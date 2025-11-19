"""
notification-service — a second, independent microservice.

Demonstrates the microservices pattern of decoupled, asynchronous
communication: this service knows nothing about the payments-api's
internals, HTTP routes, or database. It only knows about the
`transfer.settled` message contract on the shared bus.

In production this consumes from Azure Service Bus / Event Hubs (or Kafka)
and would be deployed as its own container with its own scaling policy,
independent of payments-api — e.g. it can scale to zero when there's no
traffic, while payments-api stays warm.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payments-api"))

from app.message_queue import TRANSFER_SETTLED_TOPIC, bus  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification-service")


def send_notification(event: dict) -> None:
    """Stand-in for an email/SMS/webhook dispatch."""
    logger.info(
        "Notifying wallets %s -> %s: %s %s settled (transfer_id=%s)",
        event["from_wallet"],
        event["to_wallet"],
        event["amount"],
        event["currency"],
        event["transfer_id"],
    )


def poll_forever(interval_seconds: float = 1.0) -> None:
    logger.info("notification-service started, polling '%s'", TRANSFER_SETTLED_TOPIC)
    while True:
        for event in bus.consume_all(TRANSFER_SETTLED_TOPIC):
            send_notification(event)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    poll_forever()
