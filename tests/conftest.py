"""Shared test fixtures for mcp-shopify-meta tests."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from graphql import build_client_schema

from shopify_meta.utils.schema_loader import load_schema_from_dict
from tests.fixtures.mini_schema import MINI_INTROSPECTION

# Module paths for patching
MODULE_SCHEMA_TOOLS = "shopify_meta.resources.schema"
MODULE_EXECUTE_TOOLS = "shopify_meta.resources.execute"
MODULE_ISSUE_TOOLS = "shopify_meta.resources.issues"


@pytest.fixture
def mini_schema_index():
    """A SchemaIndex built from the hand-rolled MINI_INTROSPECTION fixture."""
    return load_schema_from_dict(MINI_INTROSPECTION)


@pytest.fixture
def mock_store_config():
    """A test store config matching the StoreConfig TypedDict."""
    return {
        "store_name": "test-store",
        "shopify_url": "https://test-store.myshopify.com",
        "token": "shpat_test",
    }


@contextmanager
def _patch_schema(module_path: str):
    """Patch `get_schema` (and `get_graphql_schema` if imported) in the given
    resource module to return the mini-fixture-derived objects.

    Robust to either name being absent from the target module — we only patch
    what the module actually imported.
    """
    import importlib

    idx = load_schema_from_dict(MINI_INTROSPECTION)
    graphql_schema = build_client_schema(MINI_INTROSPECTION)

    target = importlib.import_module(module_path)
    patches = []
    if hasattr(target, "get_schema"):
        patches.append(patch(f"{module_path}.get_schema", return_value=idx))
    if hasattr(target, "get_graphql_schema"):
        patches.append(patch(f"{module_path}.get_graphql_schema", return_value=graphql_schema))

    for p in patches:
        p.start()
    try:
        yield idx
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def patch_schema():
    """Provide the patch_schema context manager as a fixture for parameterized use."""
    return _patch_schema


@contextmanager
def _mock_shopify(
    module_path: str,
    *,
    return_value=None,
    side_effect=None,
):
    """Patch `get_store_manager` + `get_graphql_client` in a resource module.

    Yields the AsyncMock GraphQL client so tests can inspect execute_query calls.
    """
    mock_store_manager = MagicMock()
    mock_store_manager.get_store_config.return_value = {
        "store_name": "test-store",
        "shopify_url": "https://test-store.myshopify.com",
        "token": "shpat_test",
    }
    mock_store_manager.list_stores.return_value = ["test-store"]

    mock_client = AsyncMock()
    if side_effect is not None:
        mock_client.execute_query.side_effect = side_effect
    else:
        mock_client.execute_query.return_value = return_value

    with patch(f"{module_path}.get_store_manager", return_value=mock_store_manager), \
         patch(f"{module_path}.get_graphql_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_shopify():
    """Provide the mock_shopify context manager as a fixture."""
    return _mock_shopify
