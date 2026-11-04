# SPDX-License-Identifier: Apache-2.0
"""Fan-out of server events to the WebSocket sessions subscribed to their topic (TC-35).

Every `/ws` session registers here while it is connected. Code that changes state (the workspace
service, later the run supervisor) calls `publish(topic, message)`; each session subscribed to
`topic` receives the message. A session whose send fails is skipped: its own receive loop notices
the disconnect and unregisters it.
"""

import logging
from typing import Protocol

from studio_backend.events import Topic, WsServerMessage

logger = logging.getLogger(__name__)


class Subscriber(Protocol):
    topics: set[str]

    async def send(self, message: WsServerMessage) -> None: ...


class EventHub:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def register(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def unregister(self, subscriber: Subscriber) -> None:
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    async def publish(self, topic: Topic, message: WsServerMessage) -> None:
        for subscriber in list(self._subscribers):
            if topic not in subscriber.topics:
                continue
            try:
                await subscriber.send(message)
            except Exception:  # a closing socket must not break the caller's request
                logger.debug("Dropped a %s event for a closing session", topic, exc_info=True)
