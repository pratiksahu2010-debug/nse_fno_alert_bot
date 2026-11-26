"""Fail-closed recovery coordinator for non-authoritative shadow actors.

Recovery is opt-in and is not connected to LiveRuntime. It reads verified
aggregate snapshots/event history, validates every checkpoint, then restores
only shadow-observation fields. It has no strategy, signal, alert, broker or
order dependencies.
"""
import asyncio
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Callable

from .shadow_runtime import ShadowActorRegistry
from ..database.replay import replay_aggregate


class RecoveryLifecycle(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RECOVERING = "RECOVERING"
    READY = "READY"
    FAILED = "FAILED"
    STOPPING = "STOPPING"


@dataclass(frozen=True)
class ShadowRecoveryReport:
    state: RecoveryLifecycle
    restored: int
    skipped: int
    details: tuple[str, ...]


class ShadowRecoveryError(RuntimeError):
    """A checkpoint could not be verified or safely applied."""


def _validate_checkpoint(instrument_key: str, state: dict) -> dict:
    if not isinstance(state, dict):
        raise ShadowRecoveryError(f"{instrument_key}: checkpoint state must be an object")
    timestamp = state.get("last_timestamp")
    price = state.get("last_price")
    processed = state.get("processed", 0)
    if not isinstance(timestamp, str) or not timestamp:
        raise ShadowRecoveryError(f"{instrument_key}: last_timestamp is missing")
    from datetime import datetime
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowRecoveryError(f"{instrument_key}: invalid last_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ShadowRecoveryError(f"{instrument_key}: last_timestamp must include a timezone")
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise ShadowRecoveryError(f"{instrument_key}: last_price must be numeric")
    if not isfinite(float(price)) or float(price) <= 0:
        raise ShadowRecoveryError(f"{instrument_key}: last_price must be finite and positive")
    if type(processed) is not int or processed < 0:
        raise ShadowRecoveryError(f"{instrument_key}: processed must be a non-negative integer")
    return {
        "last_timestamp": parsed,
        "last_price": float(price),
        "processed": processed,
    }


class ShadowRecoveryCoordinator:
    """Bounded, read-only replay followed by an all-or-nothing shadow restore."""

    def __init__(
        self,
        session_factory: Callable,
        registry: ShadowActorRegistry,
        *,
        reducers: dict,
        upcasters: dict | None = None,
        target_schema_versions: dict | None = None,
        initial_state: dict | None = None,
        aggregate_type: str = "shadow_actor",
        concurrency: int = 8,
        per_aggregate_timeout: float = 5.0,
    ):
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        if per_aggregate_timeout <= 0:
            raise ValueError("per_aggregate_timeout must be positive")
        if not isinstance(aggregate_type, str) or not aggregate_type.strip():
            raise ValueError("aggregate_type is required")
        self.session_factory = session_factory
        self.registry = registry
        self.reducers = reducers
        self.upcasters = upcasters or {}
        self.target_schema_versions = target_schema_versions or {}
        self.initial_state = initial_state or {}
        self.aggregate_type = aggregate_type
        self.concurrency = concurrency
        self.per_aggregate_timeout = per_aggregate_timeout
        self.state = RecoveryLifecycle.STOPPED
        self._lock = asyncio.Lock()

    def _replay_one(self, instrument_key: str):
        # Each worker owns its own synchronous SQLAlchemy session. Replay and
        # checksum verification are read-only; no transaction is committed.
        with self.session_factory() as session:
            return replay_aggregate(
                session,
                aggregate_type=self.aggregate_type,
                aggregate_id=instrument_key,
                reducers=self.reducers,
                upcasters=self.upcasters,
                target_schema_versions=self.target_schema_versions,
                initial_state=self.initial_state,
            )

    async def recover(self, instrument_keys) -> ShadowRecoveryReport:
        keys = tuple(dict.fromkeys(instrument_keys))
        if any(not isinstance(key, str) or not key.strip() for key in keys):
            raise ValueError("instrument keys must be non-empty strings")
        async with self._lock:
            if self.state in (RecoveryLifecycle.STOPPING, RecoveryLifecycle.STOPPED, RecoveryLifecycle.FAILED):
                self.state = RecoveryLifecycle.STARTING
            elif self.state == RecoveryLifecycle.READY:
                return ShadowRecoveryReport(self.state, 0, len(keys), ("already recovered",))
            else:
                raise ShadowRecoveryError(f"recovery cannot start from {self.state.value}")
            self.state = RecoveryLifecycle.RECOVERING
            semaphore = asyncio.Semaphore(self.concurrency)
            checkpoints = {}
            skipped = []
            try:
                async def load(key):
                    async with semaphore:
                        try:
                            replay = await asyncio.wait_for(
                                asyncio.to_thread(self._replay_one, key),
                                timeout=self.per_aggregate_timeout,
                            )
                        except asyncio.TimeoutError as exc:
                            raise ShadowRecoveryError(f"{key}: replay timed out") from exc
                        if replay.aggregate_version == 0:
                            skipped.append(key)
                            return
                        checkpoints[key] = _validate_checkpoint(key, replay.state)

                await asyncio.gather(*(load(key) for key in keys))
                # The registry validates the entire batch before mutating any
                # actor, so a corrupt checkpoint cannot cause partial restore.
                self.registry.restore_checkpoints(checkpoints)
                self.state = RecoveryLifecycle.READY
                return ShadowRecoveryReport(
                    self.state, len(checkpoints), len(skipped), tuple(skipped)
                )
            except Exception:
                self.state = RecoveryLifecycle.FAILED
                raise

    async def stop(self, timeout: float = 2.0) -> bool:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.state = RecoveryLifecycle.STOPPING
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        try:
            self.state = RecoveryLifecycle.STOPPED
            return True
        finally:
            self._lock.release()
