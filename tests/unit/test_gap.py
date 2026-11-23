from app.strategies.gap_detector import detect_gap
def test_gap_thresholds():
 assert detect_gap(101,100).classification=="NORMAL_GAP"
 assert detect_gap(103,100).classification=="EXCEPTIONAL_GAP"
