"""
Centralised logging for the application.
Replaces all print() / DEBUG statements with structured log output.
"""
import logging
import os
import sys

def get_logger(name: str) -> logging.Logger:
    """Return a named logger configured for the app environment."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    level_name = os.getenv("LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger
