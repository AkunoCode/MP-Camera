"""
Centralized logging utilities for SoilSight.

Provides a standardized logger factory that ensures all modules use consistent
formatting and handlers. Logs are written to:
- Console (DEBUG level in development, INFO in production)
- File: ~/.mpcamera/debug.log (DEBUG level always)

Usage:
    from mpcamera.logging_utils import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened")
    logger.error("Error occurred", exc_info=True)
"""

import logging
import logging.handlers
from pathlib import Path
import sys

# Global flag to track if logging has been initialized
_logging_initialized = False


def setup_logging(log_level=logging.DEBUG):
    """
    Initialize logging system. Call once at app startup from main.py.

    Args:
        log_level: minimum level for console output (file always gets DEBUG)
    """
    global _logging_initialized
    if _logging_initialized:
        return

    _logging_initialized = True

    # Create log directory
    log_dir = Path.home() / ".mpcamera"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "debug.log"

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything

    # Detailed format with module name and function
    detailed_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler (less verbose, INFO level minimum)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(
        logging.Formatter(
            '%(levelname)s - %(name)s - %(message)s'
        )
    )
    root_logger.addHandler(console_handler)

    # File handler (always DEBUG level for full debugging)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_format)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to set up file logging: {e}")


def get_logger(name):
    """
    Get a logger for a specific module.

    Args:
        name: Usually __name__ from the calling module

    Returns:
        logging.Logger: Configured logger instance

    Example:
        from mpcamera.logging_utils import get_logger
        logger = get_logger(__name__)
        logger.info("Module initialized")
    """
    return logging.getLogger(name)
