import logging
import os

_LOG_LEVEL = os.getenv("SOF_BOT_LOG", "INFO").upper()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    level = getattr(logging, _LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
