"""Bounded asynchronous producer for shadow-observation checkpoint events.

This component is opt-in and deliberately separate from LiveRuntime. It
persists only diagnostic actor observations, never trading or signal state.
"""
import asyncio
from datetime import datetime
from time import monotonic

from sqlalchemy import func, select

from ..database.event_store import append_event
from ..database.models import DomainEventRow


AGGREGATE_TYPE = "shadow_actor"
EVENT_TYPE = "ObservationCheckpointed"


def _validate_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise TypeError("checkpoint snapshot must be a dictionary")
    key = snapshot.get("instrument_key")
    stamp = snapshot.get("last_timestamp")
    price = snapshot.get("last_price")
    processed = snapshot.get("processed")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("instrument_key is required")
    if not isinstance(stamp, str) or not stamp:
        raise ValueError("last_timestamp is required")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("last_timestamp must include a timezone")
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise ValueError("last_price must be numeric")
    if not __import__("math").isfinite(float(price)) or float(price) <= 0:
        raise ValueError("last_price must be finite and positive")
    if type(processed) is not int or processed < 0:
        raise ValueError("processed must be a non-negative integer")
    return key, parsed, {
        "last_timestamp": parsed.isoformat(),
        "last_price": float(price),
        "processed": processed,
    }


class ShadowCheckpointProducer:
    """Coalesce observations by instrument and append bounded versioned events.

    Exactly one producer instance may own a given aggregate at a time. The
    event ledger's unique aggregate-version constraint remains the final
    concurrency guard. Queue submission never performs database I/O.
    """

    def __init__(
        self,
        session_factory,
        *,
        max_pending_symbols=256,
        min_interval_seconds=30.0,
        max_attempts=3,
        retry_delay_seconds=0.25,
    ):
        if max_pending_symbols < 1:
            raise ValueError("max_pending_symbols must be positive")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        self.session_factory = session_factory
        self.queue = asyncio.Queue(maxsize=max_pending_symbols)
        self.min_interval_seconds = float(min_interval_seconds)
        self.max_attempts = max_attempts
        self.retry_delay_seconds = float(retry_delay_seconds)
        self._pending = {}
        self._last_submitted = {}
        self._versions = {}
        self._task = None
        self.accepting = False
        self.submitted = 0
        self.coalesced = 0
        self.throttled = 0
        self.dropped = 0
        self.persisted = 0
        self.failed = 0
        self.last_error = None

    def start(self):
        if self._task is not None:
            return
        self.accepting = True
        self._task = asyncio.create_task(
            self._run(), name="shadow-checkpoint-producer"
        )

    def submit(self, snapshot, *, force=False):
        """Enqueue a latest-state checkpoint without blocking the actor."""
        if not self.accepting:
            self.dropped += 1
            return False
        try:
            key, occurred_at, payload = _validate_snapshot(snapshot)
        except (TypeError, ValueError, OverflowError):
            self.failed += 1
            self.last_error = "invalid_checkpoint"
            return False

        now = monotonic()
        if not force and now - self._last_submitted.get(key, 0.0) < self.min_interval_seconds:
            self.throttled += 1
            return False

        if key in self._pending:
            self._pending[key] = (payload, occurred_at)
            self.coalesced += 1
            self._last_submitted[key] = now
            return True

        try:
            self.queue.put_nowait(key)
        except asyncio.QueueFull:
            self.dropped += 1
            return False
        self._pending[key] = (payload, occurred_at)
        self._last_submitted[key] = now
        self.submitted += 1
        return True

    def _load_version(self, key):
        with self.session_factory() as session:
            return session.scalar(
                select(func.max(DomainEventRow.aggregate_version)).where(
                    DomainEventRow.aggregate_type == AGGREGATE_TYPE,
                    DomainEventRow.aggregate_id == key,
                )
            ) or 0

    def _append(self, key, version, payload, occurred_at):
        with self.session_factory() as session:
            append_event(
                session,
                aggregate_type=AGGREGATE_TYPE,
                aggregate_id=key,
                aggregate_version=version,
                event_type=EVENT_TYPE,
                schema_version=1,
                payload=payload,
                idempotency_key=f"shadow-checkpoint:{key}:{version}",
                source="shadow_actor",
                occurred_at=occurred_at,
            )
            session.commit()

    async def _persist_with_retry(self, key, payload, occurred_at):
        version = self._versions.get(key)
        if version is None:
            version = await asyncio.to_thread(self._load_version, key)
            self._versions[key] = version
        next_version = version + 1
        for attempt in range(self.max_attempts):
            try:
                await asyncio.to_thread(
                    self._append, key, next_version, payload, occurred_at
                )
                self._versions[key] = next_version
                self.persisted += 1
                self.last_error = None
                return
            except Exception as exc:
                self.last_error = type(exc).__name__
                if attempt + 1 >= self.max_attempts:
                    self.failed += 1
                    return
                await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))

    async def _run(self):
        while True:
            key = await self.queue.get()
            try:
                item = self._pending.pop(key, None)
                if item is not None:
                    payload, occurred_at = item
                    await self._persist_with_retry(key, payload, occurred_at)
            finally:
                self.queue.task_done()

    async def flush(self, timeout=5.0):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        try:
            await asyncio.wait_for(self.queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def stop(self, timeout=5.0):
        self.accepting = False
        drained = await self.flush(timeout=timeout)
        task = self._task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._task = None
        return drained

    def snapshot(self):
        return {
            "enabled": self.accepting,
            "queue_depth": self.queue.qsize(),
            "pending_symbols": len(self._pending),
            "submitted": self.submitted,
            "coalesced": self.coalesced,
            "throttled": self.throttled,
            "dropped": self.dropped,
            "persisted": self.persisted,
            "failed": self.failed,
            "last_error": self.last_error,
        }
