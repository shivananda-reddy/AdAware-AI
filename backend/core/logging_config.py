
import logging
import sys

def setup_logging():
    LOG = logging.getLogger("adaware")
    logging.basicConfig(level=logging.INFO)
    return LOG
