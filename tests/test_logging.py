"""Tests for logging helpers."""

import logging

import pytest

from shopify_meta.utils.logging import setup_logging, truncate


class TestTruncate:
    def test_none_returns_empty(self):
        assert truncate(None) == ""

    def test_short_text_unchanged(self):
        assert truncate("hello") == "hello"

    def test_text_at_max_len_unchanged(self):
        text = "a" * 2000
        assert truncate(text) == text

    def test_text_over_max_len_truncated(self):
        text = "a" * 2001
        result = truncate(text)
        assert result.endswith("... [truncated]")
        assert len(result) == 2000 + len("... [truncated]")

    def test_custom_max_len(self):
        assert truncate("hello world", max_len=5) == "hello... [truncated]"


class TestSetupLogging:
    def test_default_level_is_info(self, monkeypatch):
        monkeypatch.delenv("MCP_LOG_LEVEL", raising=False)
        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_reads_log_level_env(self, monkeypatch):
        monkeypatch.setenv("MCP_LOG_LEVEL", "DEBUG")
        # basicConfig only runs the first time; reset handlers to force re-config
        logging.getLogger().handlers.clear()
        logging.basicConfig(level=logging.INFO, force=True)
        setup_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_invalid_log_level_falls_back_to_info(self, monkeypatch):
        monkeypatch.setenv("MCP_LOG_LEVEL", "NOT_A_REAL_LEVEL")
        logging.getLogger().handlers.clear()
        logging.basicConfig(level=logging.WARNING, force=True)
        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_log_file_adds_rotating_handler(self, monkeypatch, tmp_path):
        log_file = tmp_path / "test.log"
        monkeypatch.setenv("MCP_LOG_FILE", str(log_file))
        logging.getLogger().handlers.clear()
        setup_logging()
        from logging.handlers import RotatingFileHandler

        handlers = logging.getLogger().handlers
        rotating = [h for h in handlers if isinstance(h, RotatingFileHandler)]
        assert len(rotating) == 1
        assert rotating[0].maxBytes == 5_000_000
        assert rotating[0].backupCount == 3
