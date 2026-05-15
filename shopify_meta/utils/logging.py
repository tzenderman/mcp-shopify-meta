"""Logging helpers for MCP server."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv


def setup_logging() -> None:
    """Configure logging from environment variables.

    Reads MCP_LOG_LEVEL and MCP_LOG_FILE, sets up root logger.
    """
    loaded = load_dotenv()
    if not loaded:
        package_dir = Path(__file__).resolve().parent.parent
        project_root = package_dir.parent
        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)

    log_level = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
    resolved_level = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        force=True,
    )
    logging.getLogger().setLevel(resolved_level)

    log_file = os.getenv("MCP_LOG_FILE")
    if log_file:
        try:
            handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
            )
            logging.getLogger().addHandler(handler)
        except Exception:
            pass


def truncate(text: str | None, max_len: int = 2000) -> str:
    """Truncate text to max_len with a suffix marker."""
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "... [truncated]"
