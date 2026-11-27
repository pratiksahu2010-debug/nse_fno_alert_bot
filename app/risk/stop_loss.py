from math import isfinite


def structural_stop(signal, atr_value, buffer=0.2):
    """Return a validated underlying structural stop, or None when unsafe."""
    try:
        entry = float(signal.entry)
        a = float(atr_value if atr_value is not None else signal.metadata.get("atr") or 0)
        buffer = float(buffer)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(isfinite(value) for value in (entry, a, buffer)):
        return None
    if entry <= 0 or a <= 0 or buffer < 0:
        return None

    metadata = signal.metadata
    direction = signal.direction
    if direction not in {"CALL", "PUT"}:
        return None
    level = metadata.get("or_low") if signal.module == "ORB_GAP" and direction == "CALL" else (
        metadata.get("or_high") if signal.module == "ORB_GAP" else (
            metadata.get("structure_low") if direction == "CALL" else metadata.get("structure_high")
        )
    )
    if level is None:
        return None
    try:
        level = float(level)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(level) or level <= 0:
        return None

    stop = level - buffer * a if direction == "CALL" else level + buffer * a
    if not isfinite(stop) or stop <= 0:
        return None
    if (direction == "CALL" and stop >= entry) or (direction == "PUT" and stop <= entry):
        return None
    return stop
