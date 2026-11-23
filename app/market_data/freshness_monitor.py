from datetime import datetime, timezone
class FreshnessMonitor:
    def __init__(self,max_age_seconds=90): self.max_age=max_age_seconds; self.seen={}
    def mark(self,key,when=None): self.seen[key]=when or datetime.now(timezone.utc)
    def stale(self,key,now=None):
        now=now or datetime.now(timezone.utc); return key not in self.seen or (now-self.seen[key]).total_seconds()>self.max_age
