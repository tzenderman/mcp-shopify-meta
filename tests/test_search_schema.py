"""Tests for the search_schema MCP tool."""

import pytest

from shopify_meta.resources.schema import search_schema
from tests.conftest import MODULE_SCHEMA_TOOLS


@pytest.mark.asyncio
class TestSearchSchema:
    async def test_returns_results_shape(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await search_schema(keyword="product")
        assert "results" in result
        assert "total" in result
        assert "truncated" in result

    async def test_finds_query_field(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await search_schema(keyword="shop")
        names = {r["name"] for r in result["results"]}
        assert "shop" in names

    async def test_kinds_filter(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await search_schema(keyword="product", kinds=["Mutation"])
        names = {r["name"] for r in result["results"]}
        assert names == {"productCreate", "productUpdate"}

    async def test_limit_truncates(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await search_schema(keyword="product", limit=2)
        assert len(result["results"]) == 2
        assert result["truncated"] is True

    async def test_empty_keyword_returns_structured_error(self, patch_schema):
        """Empty keyword returns a structured error instead of throwing."""
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await search_schema(keyword="")
        assert result.get("error") is not None
        assert "results" in result and result["results"] == []
