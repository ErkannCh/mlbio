from __future__ import annotations

import json
import queue
from threading import Lock
from typing import Any


class StreamBroker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscribers: dict[str, set[queue.Queue[str]]] = {}

    def subscribe(self, job_id: str) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(job_id, set()).add(q)
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue[str]) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id)
            if not subs:
                return
            subs.discard(q)
            if not subs:
                self._subscribers.pop(job_id, None)

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            subs = list(self._subscribers.get(job_id, set()))
        for q in subs:
            try:
                q.put_nowait(payload)
            except Exception:
                # Best-effort: drop if subscriber is stuck.
                pass


stream_broker = StreamBroker()

