"""Atomic domain event, projection and outbox transaction coordinator."""
from .domain_outbox import enqueue_domain_event
from .event_store import append_event
from .projections import save_projection


def append_event_with_projection_and_outbox(
    session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    event_type: str,
    event_payload: dict,
    idempotency_key: str,
    projection_state: dict,
    expected_projection_version: int,
    outbox_destination: str,
    outbox_payload: dict,
    schema_version: int = 1,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    source: str = "application",
    occurred_at=None,
):
    """Write event + read projection + outbox record in the caller's transaction.

    The caller must commit once after this function returns, or roll back on
    failure. This function does not publish, send Telegram messages or place
    orders. Its outbox record is durable intent only; a dispatcher is a later
    phase. Idempotency is enforced by the event and event/destination keys.
    """
    event = append_event(
        session,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        payload=event_payload,
        idempotency_key=idempotency_key,
        schema_version=schema_version,
        correlation_id=correlation_id,
        causation_id=causation_id,
        source=source,
        occurred_at=occurred_at,
    )
    projection = save_projection(
        session,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        state=projection_state,
        last_event_id=event.event_id,
        expected_current_version=expected_projection_version,
    )
    outbox = enqueue_domain_event(
        session,
        event_id=event.event_id,
        destination=outbox_destination,
        payload=outbox_payload,
    )
    return event, projection, outbox
