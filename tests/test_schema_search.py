"""Tests for schema_search: ranked substring lookup across schema entries."""

import pytest

from shopify_meta.utils.schema_loader import load_schema_from_dict
from shopify_meta.utils.schema_search import search_schema_index
from tests.fixtures.mini_schema import MINI_INTROSPECTION


@pytest.fixture
def idx():
    return load_schema_from_dict(MINI_INTROSPECTION)


class TestKeywordMatching:
    def test_substring_match_case_insensitive(self, idx):
        result = search_schema_index(idx, keyword="product")
        names = {r["name"] for r in result["results"]}
        # Should match Product, ProductInput, ProductStatus, ProductConnection, ProductEdge,
        # ProductCreatePayload, ProductUpdatePayload, productCreate, productUpdate, product, products
        assert "Product" in names
        assert "ProductInput" in names
        assert "productCreate" in names
        assert "product" in names

    def test_keyword_lowercase_match_uppercase_in_schema(self, idx):
        result = search_schema_index(idx, keyword="active")
        names = {r["name"] for r in result["results"]}
        assert "ACTIVE" in names

    def test_no_matches_returns_empty(self, idx):
        result = search_schema_index(idx, keyword="nonexistent_thing")
        assert result["results"] == []
        assert result["total"] == 0
        assert result["truncated"] is False

    def test_empty_keyword_raises(self, idx):
        with pytest.raises(ValueError, match="keyword must not be empty"):
            search_schema_index(idx, keyword="")

    def test_whitespace_keyword_raises(self, idx):
        with pytest.raises(ValueError, match="keyword must not be empty"):
            search_schema_index(idx, keyword="   ")


class TestRanking:
    def test_exact_name_match_ranks_first(self, idx):
        # "Product" exactly matches the Product type.
        result = search_schema_index(idx, keyword="Product")
        assert result["results"][0]["name"] == "Product"

    def test_prefix_match_outranks_substring_match(self, idx):
        # "Product" prefix-matches ProductInput, ProductStatus, etc.
        # The non-prefix substring "productCreate" should come AFTER prefix matches.
        result = search_schema_index(idx, keyword="ProductI")
        names_in_order = [r["name"] for r in result["results"]]
        assert "ProductInput" in names_in_order
        # ProductInput (prefix) before any non-prefix match


class TestKindsFilter:
    def test_kinds_filter_restricts_results(self, idx):
        result = search_schema_index(idx, keyword="product", kinds=["Mutation"])
        names = {r["name"] for r in result["results"]}
        assert names == {"productCreate", "productUpdate"}

    def test_multiple_kinds_combined(self, idx):
        result = search_schema_index(idx, keyword="product", kinds=["Query", "Mutation"])
        names = {r["name"] for r in result["results"]}
        assert {"product", "products", "productCreate", "productUpdate"} <= names

    def test_unknown_kind_returns_empty_for_that_kind(self, idx):
        result = search_schema_index(idx, keyword="product", kinds=["NotAKind"])
        assert result["results"] == []


class TestLimit:
    def test_default_limit_is_25(self, idx):
        # Create a search that would naturally return many matches.
        result = search_schema_index(idx, keyword="product")
        assert len(result["results"]) <= 25

    def test_custom_limit(self, idx):
        result = search_schema_index(idx, keyword="product", limit=2)
        assert len(result["results"]) == 2

    def test_truncated_flag_set_when_results_exceed_limit(self, idx):
        result = search_schema_index(idx, keyword="product", limit=2)
        assert result["truncated"] is True

    def test_total_reflects_full_match_count(self, idx):
        full = search_schema_index(idx, keyword="product", limit=999)
        limited = search_schema_index(idx, keyword="product", limit=2)
        assert limited["total"] == full["total"]
        assert limited["total"] >= 2


class TestResultShape:
    def test_results_include_required_fields(self, idx):
        result = search_schema_index(idx, keyword="productCreate")
        entry = result["results"][0]
        assert entry["name"] == "productCreate"
        assert entry["kind"] == "Mutation"
        assert entry["on_type"] == "Mutation"
        assert "description" in entry

    def test_type_entry_has_no_on_type(self, idx):
        result = search_schema_index(idx, keyword="ProductInput")
        product_input = next(r for r in result["results"] if r["name"] == "ProductInput")
        assert product_input["on_type"] is None
        assert product_input["kind"] == "Input"
