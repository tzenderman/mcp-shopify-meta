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


class TestRedaction:
    """Reports carry model-supplied arguments and response excerpts, which can
    contain credentials or customer PII. Both sinks (log line + JSONL) must
    receive the redacted payload."""

    def _record(self, tmp_path, monkeypatch, caplog, payload):
        path = tmp_path / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        with caplog.at_level(logging.INFO):
            record_issue(payload)
        log_line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("ISSUE_REPORT "))
        return path.read_text(), log_line

    def test_redacts_values_under_secret_keys_at_any_depth(self, tmp_path, monkeypatch, caplog):
        stored, logged = self._record(tmp_path, monkeypatch, caplog, {
            "tool_arguments": {
                "headers": {"Authorization": "Bearer abc123", "X-Shopify-Access-Token": "tok_live"},
                "stores": [{"client_secret": "s3cr3t", "password": "hunter2", "api_key": "k"}],
            },
        })
        for sink in (stored, logged):
            for leaked in ("abc123", "tok_live", "s3cr3t", "hunter2"):
                assert leaked not in sink
            assert "[REDACTED]" in sink

    def test_redacts_shopify_tokens_inside_text(self, tmp_path, monkeypatch, caplog):
        token = "shpat_" + "a1b2c3d4" * 4
        stored, logged = self._record(tmp_path, monkeypatch, caplog, {
            "error_message": f"401 using token {token}",
        })
        for sink in (stored, logged):
            assert token not in sink

    def test_masks_email_addresses(self, tmp_path, monkeypatch, caplog):
        stored, logged = self._record(tmp_path, monkeypatch, caplog, {
            "response_excerpt": '{"customer": {"email": "jane.doe@example.com"}}',
        })
        for sink in (stored, logged):
            assert "jane.doe@example.com" not in sink

    def test_keeps_debugging_data_intact(self, tmp_path, monkeypatch, caplog):
        query = 'query { order(id: "gid://shopify/Order/5551234567") { name } }'
        stored, _ = self._record(tmp_path, monkeypatch, caplog, {
            "summary": "order lookup failed",
            "tool_arguments": {"query": query, "store_name": "jean-paul"},
        })
        payload = json.loads(stored.strip())
        assert payload["tool_arguments"] == {"query": query, "store_name": "jean-paul"}
        assert payload["summary"] == "order lookup failed"
