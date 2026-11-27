class SignalCoordinator:
    """In-process signal relation and deduplication index.

    Classification is deliberately side-effect free so persistence can commit
    before this process-local index is advanced.
    """

    def __init__(self):
        self.by_symbol_day = {}
        self.ids = set()

    def classify(self, signal):
        if signal.signal_id in self.ids:
            return None
        key = (signal.symbol, signal.timestamp.date())
        prior = self.by_symbol_day.get(key, ())
        same = any(item.direction == signal.direction for item in prior)
        opposite = any(item.direction != signal.direction for item in prior)
        signal.relation = (
            "CONFLICT" if opposite
            else "CONFLUENCE" if same
            else "INDEPENDENT"
        )
        return signal

    def accept(self, signal):
        """Advance the in-memory index after durable persistence succeeds."""
        if signal.signal_id in self.ids:
            return None
        self.classify(signal)
        key = (signal.symbol, signal.timestamp.date())
        self.by_symbol_day.setdefault(key, []).append(signal)
        self.ids.add(signal.signal_id)
        return signal
