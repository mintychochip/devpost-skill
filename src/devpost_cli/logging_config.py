"""Structured logging configuration for Devpost CLI."""

import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI.

    Args:
        verbose: If True, set level to DEBUG; otherwise WARNING.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger = logging.getLogger("devpost_cli")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the devpost_cli namespace."""
    return logging.getLogger(f"devpost_cli.{name}")
