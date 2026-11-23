import logging
log=logging.getLogger("alerts")
def send(text): log.info("ALERT\n%s",text)
