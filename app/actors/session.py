"""Explicit opt-in lifecycle for shadow actor recovery and checkpoints.

This orchestration is intentionally not imported by LiveRuntime or FastAPI.
Callers must construct and start it explicitly; it owns only diagnostic
shadow-observation state and cannot invoke trading or alert subsystems.
"""
from enum import Enum

from .checkpoint_producer import ShadowCheckpointProducer
from .recovery import ShadowRecoveryCoordinator
from .shadow_runtime import ShadowActorRegistry


class ShadowSessionState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    READY = "READY"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


def _reduce_observation_checkpoint(state, payload):
    """Pure reducer for the version-1 observation checkpoint event."""
    next_state = dict(state)
    next_state.update(payload)
    return next_state


class ShadowActorSession:
    """Coordinate producer -> replay/restore -> actor start, and reverse drain.

    Startup ordering is strict:
      1. Start the checkpoint writer.
      2. Replay verified checkpoint events into an idle registry.
      3. Start actors only after the entire recovery batch validates.

    Shutdown ordering is strict:
      1. Stop accepting new observations and drain actor mailboxes.
      2. Enqueue final snapshots for actors with an observation.
      3. Flush and stop the checkpoint writer.
      4. Stop the recovery coordinator.

    This class is not wired into application startup and does not alter the
    authoritative market-data, strategy, signal, trade, risk, or alert paths.
    """

    def __init__(
        self,
        session_factory,
        instrument_keys,
        *,
        mailbox_size=256,
        max_symbols=1000,
        checkpoint_queue_size=256,
        checkpoint_interval_seconds=30.0,
        min_persist_interval_seconds=30.0,
        recovery_concurrency=8,
        recovery_timeout_seconds=5.0,
    ):
        keys = tuple(dict.fromkeys(instrument_keys))
        if any(not isinstance(key, str) or not key.strip() for key in keys):
            raise ValueError("instrument_keys must contain non-empty strings")
        if len(keys) > max_symbols:
            raise ValueError("instrument_keys exceed max_symbols")
        self.instrument_keys = keys
        self.producer = ShadowCheckpointProducer(
            session_factory,
            max_pending_symbols=checkpoint_queue_size,
            min_interval_seconds=min_persist_interval_seconds,
        )
        self.registry = ShadowActorRegistry(
            mailbox_size=mailbox_size,
            max_symbols=max_symbols,
            checkpoint_sink=self.producer.submit,
            checkpoint_interval_seconds=checkpoint_interval_seconds,
        )
        self.recovery = ShadowRecoveryCoordinator(
            session_factory,
            self.registry,
            reducers={"ObservationCheckpointed": _reduce_observation_checkpoint},
            concurrency=recovery_concurrency,
            per_aggregate_timeout=recovery_timeout_seconds,
        )
        self.state = ShadowSessionState.STOPPED

    async def start(self):
        if self.state == ShadowSessionState.READY:
            return self.recovery.state
        if self.state != ShadowSessionState.STOPPED:
            raise RuntimeError(f"cannot start shadow session from {self.state.value}")
        self.state = ShadowSessionState.STARTING
        self.producer.start()
        try:
            report = await self.recovery.recover(self.instrument_keys)
            self.registry.start()
            self.state = ShadowSessionState.READY
            return report
        except Exception:
            # Recovery is fail-closed: actors have not started if replay or
            # batch validation fails. Stop the writer before surfacing error.
            await self.producer.stop()
            self.state = ShadowSessionState.FAILED
            raise

    def submit(self, tick):
        """Submit only while the explicitly-started shadow session is ready."""
        if self.state != ShadowSessionState.READY:
            return False
        return self.registry.submit(tick)

    async def stop(self, *, flush_timeout=5.0):
        if flush_timeout <= 0:
            raise ValueError("flush_timeout must be positive")
        if self.state == ShadowSessionState.STOPPED:
            return True
        if self.state not in (ShadowSessionState.READY, ShadowSessionState.STOPPING, ShadowSessionState.FAILED):
            raise RuntimeError(f"cannot stop shadow session from {self.state.value}")
        self.state = ShadowSessionState.STOPPING

        # Registry stops accepting first and drains all already accepted ticks.
        actors_drained = await self.registry.stop(timeout=flush_timeout)
        if not actors_drained:
            return False

        # Actor callbacks are cadence-limited. Force one final observation
        # checkpoint after the mailbox drain, while the writer is still live.
        for actor in self.registry.actors.values():
            if actor.last_timestamp is not None:
                self.producer.submit(actor.snapshot(), force=True)

        drained = await self.producer.flush(timeout=flush_timeout)
        if not drained:
            return False
        stopped = await self.producer.stop(timeout=flush_timeout)
        if not stopped:
            return False
        await self.recovery.stop(timeout=flush_timeout)
        self.state = ShadowSessionState.STOPPED
        return True

    def snapshot(self):
        return {
            "state": self.state.value,
            "registry": self.registry.snapshot(),
            "checkpoint_producer": self.producer.snapshot(),
            "recovery_state": self.recovery.state.value,
        }
