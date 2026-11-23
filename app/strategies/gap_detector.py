from dataclasses import dataclass
@dataclass
class Gap:
    pct:float; direction:str; classification:str

def detect_gap(open_price,previous_close,min_gap=1.0):
    if previous_close<=0: raise ValueError("previous close must be positive")
    pct=(open_price-previous_close)/previous_close*100; a=abs(pct)
    cls="NO_GAP" if a<min_gap else "NORMAL_GAP" if a<2 else "STRONG_GAP" if a<3 else "EXCEPTIONAL_GAP"
    return Gap(pct,"GAP_UP" if pct>0 else "GAP_DOWN" if pct<0 else "FLAT",cls)
