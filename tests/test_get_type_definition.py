"""Tests for the get_type_definition MCP tool."""

import pytest
from graphql import parse

from shopify_meta.resources.schema import get_type_definition
from tests.conftest import MODULE_SCHEMA_TOOLS


@pytest.mark.asyncio
class TestGetTypeDefinition:
    async def test_returns_sdl_and_metadata(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="Product")
        assert result["name"] == "Product"
        assert result["kind"] == "OBJECT"
        assert "sdl" in result
        # SDL should parse as valid GraphQL
        parse(result["sdl"])

    async def test_includes_fields_for_object(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="Product")
        field_names = {f["name"] for f in result["fields"]}
        assert {"id", "title", "status", "handle"} <= field_names

    async def test_includes_input_fields_for_input_type(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="ProductInput")
        assert result["kind"] == "INPUT_OBJECT"
        field_names = {f["name"] for f in result["input_fields"]}
        assert {"title", "status"} <= field_names

    async def test_includes_enum_values_for_enum(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="ProductStatus")
        assert result["kind"] == "ENUM"
        value_names = {v["name"] for v in result["enum_values"]}
        assert {"ACTIVE", "ARCHIVED", "DRAFT"} <= value_names

    async def test_unknown_type_returns_error(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="NoSuchType")
        assert result.get("error") is not None
        assert "NoSuchType" in result["error"]

    async def test_depth_1_does_not_expand_referenced_types(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="Product", depth=1)
        # Only the Product SDL — no inline Shop/ProductStatus definition.
        assert "type Product" in result["sdl"]
        assert "enum ProductStatus" not in result["sdl"]
        assert result.get("referenced_types") is None or result["referenced_types"] == []

    async def test_depth_2_expands_referenced_types(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="Product", depth=2)
        # Product references ProductStatus (an enum) — should be inlined.
        assert "enum ProductStatus" in result["sdl"]
        assert "ProductStatus" in result["referenced_types"]

    async def test_depth_capped_at_2(self, patch_schema):
        with patch_schema(MODULE_SCHEMA_TOOLS):
            r2 = await get_type_definition(type_name="Product", depth=2)
            r99 = await get_type_definition(type_name="Product", depth=99)
        # Same content (capped behavior).
        assert r2["sdl"] == r99["sdl"]

    async def test_skips_scalars_when_expanding(self, patch_schema):
        """depth=2 should NOT inline built-in scalars like String/ID."""
        with patch_schema(MODULE_SCHEMA_TOOLS):
            result = await get_type_definition(type_name="Product", depth=2)
        # Don't redundantly expand String, ID, Int.
        assert "scalar String" not in result["sdl"]
        assert "scalar ID" not in result["sdl"]
