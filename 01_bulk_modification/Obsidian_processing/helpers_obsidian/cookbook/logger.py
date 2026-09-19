import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cookbook")


def get_logger():
    return logger
