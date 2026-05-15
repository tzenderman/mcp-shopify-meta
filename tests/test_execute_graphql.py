"""Tests for the execute_graphql MCP tool."""

import pytest

from shopify_meta.resources.execute import execute_graphql
from shopify_meta.utils.errors import ShopifyAPIError, ShopifyAuthError
from tests.conftest import MODULE_EXECUTE_TOOLS


@pytest.mark.asyncio
class TestExecuteGraphqlValidation:
    """Validation errors return structured responses and never make a network call."""

    async def test_syntax_error_returns_structured(self, patch_schema, mock_shopify):
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS) as client:
            result = await execute_graphql(
                query="{ shop { ", store_name="test-store"
            )
        assert result["data"] is None
        assert result["errors"]
        assert any("syntax" in e["message"].lower() or "expected" in e["message"].lower()
                   for e in result["errors"])
        client.execute_query.assert_not_called()

    async def test_unknown_field_returns_structured(self, patch_schema, mock_shopify):
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS) as client:
            result = await execute_graphql(
                query="{ shop { notARealField } }", store_name="test-store"
            )
        assert result["data"] is None
        assert any("notARealField" in e["message"] for e in result["errors"])
        client.execute_query.assert_not_called()

    async def test_missing_variable_returns_structured(self, patch_schema, mock_shopify):
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS) as client:
            result = await execute_graphql(
                query='query Q($id: ID!) { product(id: $id) { id } }',
                store_name="test-store",
                variables={},
            )
        assert result["errors"]
        client.execute_query.assert_not_called()


@pytest.mark.asyncio
class TestExecuteGraphqlSuccess:
    async def test_successful_query_returns_data(self, patch_schema, mock_shopify):
        body = {"data": {"shop": {"name": "Test Shop"}}}
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS, return_value=body) as client:
            result = await execute_graphql(query="{ shop { name } }", store_name="test-store")
        assert result["data"] == {"shop": {"name": "Test Shop"}}
        assert result.get("errors") is None or result["errors"] == []
        client.execute_query.assert_called_once()

    async def test_extensions_cost_passed_through(self, patch_schema, mock_shopify):
        body = {
            "data": {"shop": {"name": "Test"}},
            "extensions": {
                "cost": {
                    "requestedQueryCost": 5,
                    "actualQueryCost": 4,
                    "throttleStatus": {"maximumAvailable": 1000.0},
                }
            },
        }
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS, return_value=body):
            result = await execute_graphql(query="{ shop { name } }", store_name="test-store")
        assert result["cost"] == {
            "requestedQueryCost": 5,
            "actualQueryCost": 4,
            "throttleStatus": {"maximumAvailable": 1000.0},
        }

    async def test_graphql_errors_returned_as_data(self, patch_schema, mock_shopify):
        """200-status responses with `errors` come back to the model as-is."""
        body = {"errors": [{"message": "Field unavailable"}], "data": None}
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS, return_value=body):
            result = await execute_graphql(query="{ shop { name } }", store_name="test-store")
        assert result["errors"] == [{"message": "Field unavailable"}]
        assert result["data"] is None

    async def test_passes_variables_and_operation_name(self, patch_schema, mock_shopify):
        body = {"data": {"product": {"id": "gid://shopify/Product/1"}}}
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS, return_value=body) as client:
            await execute_graphql(
                query='query GetIt($id: ID!) { product(id: $id) { id } }',
                store_name="test-store",
                variables={"id": "gid://shopify/Product/1"},
                operation_name="GetIt",
            )
        kwargs = client.execute_query.call_args.kwargs
        args = client.execute_query.call_args.args
        # accept positional or keyword for the GraphQL call
        called_query = kwargs.get("query") or args[1]
        called_vars = kwargs.get("variables") or (args[2] if len(args) > 2 else None)
        called_op = kwargs.get("operation_name") or (args[3] if len(args) > 3 else None)
        assert "product(id: $id)" in called_query
        assert called_vars == {"id": "gid://shopify/Product/1"}
        assert called_op == "GetIt"


@pytest.mark.asyncio
class TestExecuteGraphqlStoreErrors:
    async def test_missing_store_name_returns_error(self, patch_schema, mock_shopify):
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(MODULE_EXECUTE_TOOLS) as client:
            result = await execute_graphql(query="{ shop { name } }", store_name="")
        assert result["errors"]
        assert "store_name" in result["errors"][0]["message"]
        client.execute_query.assert_not_called()


@pytest.mark.asyncio
class TestExecuteGraphqlTransportErrors:
    """Transport-level failures bubble up as exceptions (re-raised)."""

    async def test_auth_error_raises(self, patch_schema, mock_shopify):
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(
            MODULE_EXECUTE_TOOLS, side_effect=ShopifyAuthError("bad token", store_name="test-store")
        ):
            with pytest.raises(ShopifyAuthError):
                await execute_graphql(query="{ shop { name } }", store_name="test-store")

    async def test_api_error_raises(self, patch_schema, mock_shopify):
        with patch_schema(MODULE_EXECUTE_TOOLS), mock_shopify(
            MODULE_EXECUTE_TOOLS, side_effect=ShopifyAPIError("500 retries exhausted", store_name="test-store")
        ):
            with pytest.raises(ShopifyAPIError):
                await execute_graphql(query="{ shop { name } }", store_name="test-store")
