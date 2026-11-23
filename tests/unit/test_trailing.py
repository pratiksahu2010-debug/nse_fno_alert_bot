from app.risk.trailing_stop import ratchet_stop
def test_stop_never_moves_back():
 assert ratchet_stop("CALL",100,95,98)==100
 assert ratchet_stop("PUT",100,105,102)==100
