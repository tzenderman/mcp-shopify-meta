"""Tests for the report_issue MCP tool."""

import json
import re

import pytest

from shopify_meta.resources.issues import report_issue


@pytest.mark.asyncio
class TestReportIssue:
    async def test_successful_report_returns_id_and_friendly_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.jsonl"))
        result = await report_issue(
            summary="thing broke",
            tool_name="execute_graphql",
            tool_arguments={"query": "{ shop { name } }", "store_name": "main"},
            observed_behavior="got 200 but no shop",
            expected_behavior="should have the shop",
        )
        assert re.fullmatch(r"rpt_[0-9a-f]{8}", result["report_id"])
        assert result["stored_in_file"] is True
        assert result["stored_in_log"] is True
        assert "thanks" in result and isinstance(result["thanks"], str)

    async def test_jsonl_contains_all_required_fields(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        await report_issue(
            summary="thing broke",
            tool_name="execute_graphql",
            tool_arguments={"query": "x", "store_name": "main"},
            observed_behavior="x",
            expected_behavior="y",
        )
        payload = json.loads(path.read_text().strip())
        assert payload["summary"] == "thing broke"
        assert payload["tool_name"] == "execute_graphql"
        assert payload["tool_arguments"]["store_name"] == "main"
        assert payload["observed_behavior"] == "x"
        assert payload["expected_behavior"] == "y"

    async def test_optional_fields_passthrough(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        await report_issue(
            summary="x",
            tool_name="execute_graphql",
            tool_arguments={"a": 1},
            observed_behavior="o",
            expected_behavior="e",
            severity="high",
            store_name="main",
            error_message="ShopifyAPIError: boom",
            response_excerpt="some body",
            client_context="claude opus 4.7",
        )
        payload = json.loads(path.read_text().strip())
        assert payload["severity"] == "high"
        assert payload["store_name"] == "main"
        assert payload["error_message"] == "ShopifyAPIError: boom"
        assert payload["response_excerpt"] == "some body"
        assert payload["client_context"] == "claude opus 4.7"

    async def test_response_excerpt_truncated_at_2000(self, tmp_path, monkeypatch):
        path = tmp_path / "issues.jsonl"
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(path))
        huge = "X" * 5000
        await report_issue(
            summary="x",
            tool_name="execute_graphql",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
            response_excerpt=huge,
        )
        payload = json.loads(path.read_text().strip())
        assert payload["response_excerpt"].endswith("... [truncated]")
        assert len(payload["response_excerpt"]) <= 2050

    async def test_invalid_severity_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.jsonl"))
        result = await report_issue(
            summary="x",
            tool_name="execute_graphql",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
            severity="critical",  # not allowed
        )
        assert "error" in result
        assert "severity" in result["error"].lower()

    async def test_invalid_tool_name_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.jsonl"))
        result = await report_issue(
            summary="x",
            tool_name="not_a_real_tool",  # not allowed
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
        )
        assert "error" in result
        assert "tool_name" in result["error"].lower()

    async def test_required_fields_validated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", str(tmp_path / "issues.jsonl"))
        # Empty summary should be rejected
        result = await report_issue(
            summary="",
            tool_name="execute_graphql",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
        )
        assert "error" in result

    async def test_file_failure_still_returns_success(self, monkeypatch):
        monkeypatch.setenv("ISSUE_REPORT_PATH", "/dev/null/cannot/issues.jsonl")
        result = await report_issue(
            summary="x",
            tool_name="execute_graphql",
            tool_arguments={},
            observed_behavior="o",
            expected_behavior="e",
        )
        assert result["report_id"].startswith("rpt_")
        assert result["stored_in_file"] is False
        assert result["stored_in_log"] is True
