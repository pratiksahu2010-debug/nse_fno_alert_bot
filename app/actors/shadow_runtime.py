"""Bounded per-symbol virtual actors for non-authoritative shadow observation.

These actors intentionally do not evaluate strategies, persist signals, manage
trades, or send alerts. The existing LiveRuntime remains authoritative.
"""
import asyncio


_STOP = object()


class SymbolActor:
    def __init__(self, instrument_key, mailbox_size=256):
        if mailbox_size < 1:
            raise ValueError("mailbox_size must be positive")
        self.instrument_key = instrument_key
        self.mailbox = asyncio.Queue(maxsize=mailbox_size)
        self.accepting = True
        self.processed = 0
        self.dropped = 0
        self.last_timestamp = None
        self.last_price = None
        self.task = None

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
                self.last_timestamp = item.timestamp
                self.last_price = float(item.price)
                self.processed += 1
            finally:
                self.mailbox.task_done()

    async def stop(self):
        self.accepting = False
        if self.task is None:
            return
        await self.mailbox.join()
        await self.mailbox.put(_STOP)
        await self.task
        self.task = None

    def snapshot(self):
        return {
            "instrument_key": self.instrument_key,
            "queue_depth": self.mailbox.qsize(),
            "queue_capacity": self.mailbox.maxsize,
            "processed": self.processed,
            "dropped": self.dropped,
            "last_timestamp": (
                self.last_timestamp.isoformat() if self.last_timestamp else None
            ),
        }


class ShadowActorRegistry:
    """Owns lazily-created symbol actors and enforces global actor bounds."""

    def __init__(self, mailbox_size=256, max_symbols=1000):
        if max_symbols < 1:
            raise ValueError("max_symbols must be positive")
        self.mailbox_size = mailbox_size
        self.max_symbols = max_symbols
        self.actors = {}
        self.accepting = False
        self.rejected_symbols = 0

    def start(self):
        self.accepting = True

    def submit(self, tick):
        if not self.accepting:
            return False
        actor = self.actors.get(tick.instrument_key)
        if actor is None:
            if len(self.actors) >= self.max_symbols:
                self.rejected_symbols += 1
                return False
            actor = SymbolActor(tick.instrument_key, self.mailbox_size)
            self.actors[tick.instrument_key] = actor
            actor.start()
        return actor.submit(tick)

    async def stop(self):
        self.accepting = False
        if self.actors:
            await asyncio.gather(*(actor.stop() for actor in self.actors.values()))

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
            "rejected_symbols": self.rejected_symbols,
            "actors": actors,
        }
