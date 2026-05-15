"""Tests for FastMCP server registration."""

import json

import pytest

from shopify_meta.server import create_mcp_server

EXPECTED_TOOLS = {
    "search_schema",
    "get_type_definition",
    "execute_graphql",
    "report_issue",
}


@pytest.mark.asyncio
async def test_all_tools_registered(monkeypatch, tmp_path):
    """Server should register exactly the 4 generic tools — no more, no less."""
    schema_path = tmp_path / "schema.json"
    from tests.fixtures.mini_schema import MINI_INTROSPECTION

    schema_path.write_text(json.dumps(MINI_INTROSPECTION))
    monkeypatch.setenv("SHOPIFY_SCHEMA_PATH", str(schema_path))

    mcp = create_mcp_server()
    tools = await mcp.get_tools()
    assert set(tools.keys()) == EXPECTED_TOOLS, (
        f"unexpected tools registered: extra={set(tools.keys()) - EXPECTED_TOOLS}, "
        f"missing={EXPECTED_TOOLS - set(tools.keys())}"
    )


def test_server_name_and_instructions(monkeypatch, tmp_path):
    schema_path = tmp_path / "schema.json"
    from tests.fixtures.mini_schema import MINI_INTROSPECTION

    schema_path.write_text(json.dumps(MINI_INTROSPECTION))
    monkeypatch.setenv("SHOPIFY_SCHEMA_PATH", str(schema_path))

    mcp = create_mcp_server()
    assert "Shopify Admin Meta" in mcp.name
    # instructions should mention the schema-walking pattern
    assert "schema" in (mcp.instructions or "").lower()
