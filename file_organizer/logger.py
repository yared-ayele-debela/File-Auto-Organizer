"""
Logging configuration for File Auto-Organizer.

Provides formatted console output with colors and a RotatingFileHandler
for persistent audit logging of all file movements and errors.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ANSI escape codes for terminal output
COLOR_RESET = "\033[0m"
COLOR_DEBUG = "\033[36m"    # Cyan
COLOR_INFO = "\033[32m"     # Green
COLOR_WARNING = "\033[33m"  # Yellow
COLOR_ERROR = "\033[31m"    # Red
COLOR_CRITICAL = "\033[35m" # Magenta
COLOR_BOLD = "\033[1m"


class ColoredConsoleFormatter(logging.Formatter):
    """Custom formatter providing ANSI colors for console output."""

    LEVEL_COLORS = {
        logging.DEBUG: COLOR_DEBUG,
        logging.INFO: COLOR_INFO,
        logging.WARNING: COLOR_WARNING,
        logging.ERROR: COLOR_ERROR,
        logging.CRITICAL: COLOR_CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, COLOR_RESET)
        record_copy = logging.makeLogRecord(record.__dict__)
        record_copy.levelname = f"{color}{COLOR_BOLD}{record.levelname:<8}{COLOR_RESET}"
        return super().format(record_copy)


def setup_logger(
    log_file: Path | str | None = None,
    level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    verbose: bool = False,
) -> logging.Logger:
    """
    Initialize and configure the root or application logger.

    Args:
        log_file: Path to rotating log file. If None, only console is used.
        level: Minimum log level string (DEBUG, INFO, WARNING, ERROR).
        max_bytes: Maximum size in bytes before rotating log file.
        backup_count: Number of rotated backup log files to retain.
        verbose: If True, forces level to DEBUG.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger("file_organizer")
    effective_level = logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(effective_level)

    # Clear any existing handlers to allow clean re-initialization
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(effective_level)
    console_fmt = "%(asctime)s [%(levelname)s] %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # Use colors only if stdout is an interactive TTY
    if sys.stdout.isatty():
        console_formatter = ColoredConsoleFormatter(fmt=console_fmt, datefmt=date_fmt)
    else:
        console_formatter = logging.Formatter(fmt=console_fmt, datefmt=date_fmt)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler
    if log_file:
        file_path = Path(log_file).expanduser().resolve()
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                filename=file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(effective_level)
            file_fmt = "%(asctime)s [%(levelname)-8s] [%(name)s] %(message)s"
            file_formatter = logging.Formatter(fmt=file_fmt, datefmt=date_fmt)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning(f"Could not initialize rotating log file at '{file_path}': {e}")

    return logger


def get_logger() -> logging.Logger:
    """Return the application logger."""
    return logging.getLogger("file_organizer")
