"""Tests for record_issue: the JSONL + log writer behind report_issue."""

import json
import logging
import re
import sys

import pytest

from shopify_meta.utils.issue_reporter import record_issue


class TestRecordIssue:
    def test_returns_report_id_and_file_flag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.jsonl"))
        report_id, wrote_to_file = record_issue({"summary": "x"})
        assert report_id.startswith("rpt_")
        assert wrote_to_file is True

    def test_report_id_format(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.jsonl"))
        report_id, _ = record_issue({"summary": "x"})
        assert re.fullmatch(r"rpt_[0-9a-f]{8}", report_id), report_id

    def test_appends_jsonl_line(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "first"})
        record_issue({"summary": "second"})
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["summary"] == "first"
        assert json.loads(lines[1])["summary"] == "second"

    def test_stamps_required_metadata(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "x"})
        payload = json.loads(path.read_text().strip())
        assert payload["report_id"].startswith("rpt_")
        assert payload["timestamp"]  # ISO 8601
        assert payload["server"] == "mcp-shopify-meta"
        assert payload["server_version"]
        assert payload["python_version"] == sys.version.split()[0]

    def test_caller_payload_overrides_unprotected_keys(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        # `summary` is caller-supplied; metadata keys are server-supplied and should win.
        record_issue({"summary": "caller", "report_id": "rpt_evil!"})
        payload = json.loads(path.read_text().strip())
        assert payload["summary"] == "caller"
        # report_id stamped by the server, not the caller
        assert re.fullmatch(r"rpt_[0-9a-f]{8}", payload["report_id"])

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        path = tmp_path / "nested" / "deeper" / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        record_issue({"summary": "x"})
        assert path.exists()

    def test_unwritable_path_falls_back_to_log_only(self, monkeypatch, caplog):
        # Point at a path inside a regular file (cannot mkdir over a file).
        monkeypatch.setenv("ISSUE_REPORT_PATH", "/dev/null/cannot-create/issues.jsonl")
        with caplog.at_level(logging.INFO):
            report_id, wrote_to_file = record_issue({"summary": "boom"})
        assert wrote_to_file is False
        assert report_id.startswith("rpt_")
        # Log line still emitted
        assert any("ISSUE_REPORT" in rec.message for rec in caplog.records)

    def test_always_logs_structured_line(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.jsonl"))
        with caplog.at_level(logging.INFO, logger="shopify_meta.utils.issue_reporter"):
            record_issue({"summary": "logme"})
        log_messages = [r.message for r in caplog.records if "ISSUE_REPORT" in r.message]
        assert log_messages, "expected an ISSUE_REPORT log line"
        json_portion = log_messages[0].split("ISSUE_REPORT ", 1)[1]
        parsed = json.loads(json_portion)
        assert parsed["summary"] == "logme"
