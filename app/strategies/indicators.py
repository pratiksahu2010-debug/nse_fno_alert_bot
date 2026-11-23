import numpy as np

def ema(values,period): return values.ewm(span=period,adjust=False,min_periods=period).mean()
def atr(df,period=14):
    prev=df.close.shift(1); tr=np.maximum(df.high-df.low,np.maximum((df.high-prev).abs(),(df.low-prev).abs()))
    return tr.rolling(period,min_periods=period).mean()
def relative_volume(df,period=20):
    # Current bar vs average of preceding bars only; excludes current bar from baseline.
    base=df.volume.shift(1).rolling(period,min_periods=period).mean()
    return df.volume/base.replace(0,np.nan)
