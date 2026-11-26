"""Bounded per-symbol virtual actors for non-authoritative shadow observation.

These actors intentionally do not evaluate strategies, persist signals, manage
trades, or send alerts. The existing LiveRuntime remains authoritative.
"""
import asyncio
from datetime import datetime
import math
from time import monotonic


_STOP = object()


class SymbolActor:
    def __init__(self, instrument_key, mailbox_size=256, checkpoint_sink=None, checkpoint_interval_seconds=30.0):
        if mailbox_size < 1:
            raise ValueError("mailbox_size must be positive")
        self.instrument_key = instrument_key
        self.mailbox = asyncio.Queue(maxsize=mailbox_size)
        self.accepting = True
        self.processed = 0
        self.dropped = 0
        self.failed = 0
        self.last_error = None
        self.last_timestamp = None
        self.last_price = None
        self.task = None
        if checkpoint_interval_seconds < 0:
            raise ValueError("checkpoint_interval_seconds cannot be negative")
        self.checkpoint_sink = checkpoint_sink
        self.checkpoint_interval_seconds = float(checkpoint_interval_seconds)
        self._last_checkpoint_at = None

    def restore_checkpoint(self, checkpoint):
        """Restore validated observation-only state before the actor starts."""
        if self.task is not None or not self.mailbox.empty():
            raise RuntimeError("checkpoint restore requires an idle, unstarted actor")
        timestamp = checkpoint.get("last_timestamp")
        price = checkpoint.get("last_price")
        processed = checkpoint.get("processed", 0)
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            raise ValueError("checkpoint timestamp must be timezone-aware")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 0:
            raise ValueError("checkpoint price must be finite and positive")
        if type(processed) is not int or processed < 0:
            raise ValueError("checkpoint processed count must be non-negative")
        self.last_timestamp = timestamp
        self.last_price = float(price)
        self.processed = processed

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(
                self._run(), name=f"shadow-symbol-{self.instrument_key}"
            )

    def submit(self, tick):
        if not self.accepting:
            self.dropped += 1
            return False
        try:
            self.mailbox.put_nowait(tick)
            return True
        except asyncio.QueueFull:
            # Shadow observations are best-effort. Never back-pressure the
            # production signal pipeline when this diagnostic mailbox is full.
            self.dropped += 1
            return False

    async def _run(self):
        while True:
            item = await self.mailbox.get()
            try:
                if item is _STOP:
                    return
                try:
                    self.last_timestamp = item.timestamp
                    self.last_price = float(item.price)
                    self.processed += 1
                    if self.checkpoint_sink is not None:
                        now = monotonic()
                        if (
                            self._last_checkpoint_at is None
                            or now - self._last_checkpoint_at >= self.checkpoint_interval_seconds
                        ):
                            self._last_checkpoint_at = now
                            try:
                                self.checkpoint_sink(self.snapshot())
                            except Exception as exc:
                                self.failed += 1
                                self.last_error = type(exc).__name__
                except Exception as exc:
                    # A malformed shadow observation must not kill the actor
                    # or interfere with the authoritative market-data path.
                    self.failed += 1
                    self.last_error = type(exc).__name__
            finally:
                self.mailbox.task_done()

    async def stop(self, timeout=5.0):
        """Stop accepting work and drain within a bounded, retryable timeout."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.accepting = False
        task = self.task
        if task is None:
            return True

        # If the consumer failed unexpectedly, Queue.join() could wait
        # forever because queued items would never receive task_done().
        if task.done():
            while True:
                try:
                    self.mailbox.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self.mailbox.task_done()
        else:
            try:
                await asyncio.wait_for(self.mailbox.join(), timeout=timeout)
            except asyncio.TimeoutError:
                # Leave the consumer alive; callers can retry after it drains.
                return False
            if not task.done():
                await self.mailbox.put(_STOP)

        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError:
            # Do not cancel a worker that may still be finishing accepted work.
            return False
        except asyncio.CancelledError:
            # A cancelled/failed consumer cannot drain any remaining queue items.
            while True:
                try:
                    self.mailbox.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self.mailbox.task_done()
        except Exception:
            # Preserve the old shutdown guarantee: a crashed consumer must not
            # prevent cleanup or leave queued items counted as unfinished.
            while True:
                try:
                    self.mailbox.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self.mailbox.task_done()
        await asyncio.gather(task, return_exceptions=True)
        self.task = None
        return True

    def snapshot(self):
        return {
            "instrument_key": self.instrument_key,
            "queue_depth": self.mailbox.qsize(),
            "queue_capacity": self.mailbox.maxsize,
            "processed": self.processed,
            "dropped": self.dropped,
            "failed": self.failed,
            "last_error": self.last_error,
            "last_timestamp": (
                self.last_timestamp.isoformat() if self.last_timestamp else None
            ),
            "last_price": self.last_price,
        }


class ShadowActorRegistry:
    """Owns lazily-created symbol actors and enforces global actor bounds."""

    def __init__(self, mailbox_size=256, max_symbols=1000, checkpoint_sink=None, checkpoint_interval_seconds=30.0):
        if max_symbols < 1:
            raise ValueError("max_symbols must be positive")
        if mailbox_size < 1:
            raise ValueError("mailbox_size must be positive")
        self.mailbox_size = mailbox_size
        self.max_symbols = max_symbols
        self.actors = {}
        self.accepting = False
        self.rejected_symbols = 0
        if checkpoint_interval_seconds < 0:
            raise ValueError("checkpoint_interval_seconds cannot be negative")
        self.checkpoint_sink = checkpoint_sink
        self.checkpoint_interval_seconds = float(checkpoint_interval_seconds)

    def restore_checkpoints(self, checkpoints):
        """Atomically seed actors before they start consuming ticks."""
        if self.accepting:
            raise RuntimeError("cannot restore checkpoints after registry start")
        if not isinstance(checkpoints, dict):
            raise TypeError("checkpoints must be a dictionary")
        if self.actors:
            raise RuntimeError("checkpoint restore requires an empty registry")
        if len(checkpoints) > self.max_symbols:
            raise ValueError("checkpoint set exceeds actor registry capacity")
        # Validate every checkpoint before creating any actor.
        for key, value in checkpoints.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(value, dict):
                raise ValueError("invalid actor checkpoint entry")
            timestamp = value.get("last_timestamp")
            price = value.get("last_price")
            processed = value.get("processed", 0)
            if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
                raise ValueError("checkpoint timestamp must be timezone-aware")
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 0:
                raise ValueError("checkpoint price must be finite and positive")
            if type(processed) is not int or processed < 0:
                raise ValueError("checkpoint processed count must be non-negative")
        restored = {}
        for key, value in checkpoints.items():
            actor = SymbolActor(key, self.mailbox_size, self.checkpoint_sink, self.checkpoint_interval_seconds)
            actor.restore_checkpoint(value)
            restored[key] = actor
        self.actors.update(restored)
        return len(restored)

    def start(self):
        self.accepting = True
        for actor in self.actors.values():
            actor.start()

    def submit(self, tick):
        if not self.accepting:
            return False
        actor = self.actors.get(tick.instrument_key)
        if actor is None:
            if len(self.actors) >= self.max_symbols:
                self.rejected_symbols += 1
                return False
            actor = SymbolActor(tick.instrument_key, self.mailbox_size, self.checkpoint_sink, self.checkpoint_interval_seconds)
            self.actors[tick.instrument_key] = actor
            actor.start()
        return actor.submit(tick)

    async def stop(self, timeout=5.0):
        """Stop every actor; return false if any mailbox cannot drain in time."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.accepting = False
        if not self.actors:
            return True
        results = await asyncio.gather(
            *(actor.stop(timeout=timeout) for actor in self.actors.values())
        )
        return all(results)

    def snapshot(self):
        actors = [actor.snapshot() for actor in self.actors.values()]
        return {
            "enabled": self.accepting,
            "actor_count": len(actors),
            "max_symbols": self.max_symbols,
            "mailbox_capacity": self.mailbox_size,
            "queue_depth": sum(item["queue_depth"] for item in actors),
            "processed": sum(item["processed"] for item in actors),
            "dropped": sum(item["dropped"] for item in actors),
            "failed": sum(item["failed"] for item in actors),
            "last_error": next(
                (item["last_error"] for item in reversed(actors) if item["last_error"]),
                None,
            ),
            "rejected_symbols": self.rejected_symbols,
            "actors": actors,
        }
