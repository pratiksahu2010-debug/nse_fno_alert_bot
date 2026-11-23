import pandas as pd
from app.strategies.momentum_explosion import MomentumExplosionStrategy
def test_requires_warmup():
 df=pd.DataFrame({"open":[1]*20,"high":[2]*20,"low":[.5]*20,"close":[1]*20,"volume":[100]*20},index=pd.date_range("2026-01-01 09:15",periods=20,freq="5min"))
 assert MomentumExplosionStrategy().evaluate("ABC",df) is None
