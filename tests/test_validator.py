"""Tests for the GraphQL validator: parse + validate + coerce_variables."""

import pytest
from graphql import build_client_schema

from shopify_meta.utils.validator import validate_query
from tests.fixtures.mini_schema import MINI_INTROSPECTION


@pytest.fixture
def schema():
    return build_client_schema(MINI_INTROSPECTION)


class TestParse:
    def test_valid_query_passes(self, schema):
        result = validate_query(schema, "{ shop { name } }")
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["coerced_variables"] == {}

    def test_syntax_error_returns_structured(self, schema):
        result = validate_query(schema, "{ shop { ")
        assert result["valid"] is False
        assert any("syntax" in e["message"].lower() or "expected" in e["message"].lower()
                   for e in result["errors"])

    def test_syntax_error_includes_location(self, schema):
        result = validate_query(schema, "{ shop { ")
        assert result["valid"] is False
        assert result["errors"][0].get("locations") is not None
        assert isinstance(result["errors"][0]["locations"], list)
        assert "line" in result["errors"][0]["locations"][0]


class TestValidate:
    def test_unknown_field_fails(self, schema):
        result = validate_query(schema, "{ shop { totallyUnknownField } }")
        assert result["valid"] is False
        msgs = " ".join(e["message"] for e in result["errors"])
        assert "totallyUnknownField" in msgs

    def test_unknown_root_query_fails(self, schema):
        result = validate_query(schema, "{ unknownRoot { id } }")
        assert result["valid"] is False

    def test_missing_required_arg_fails(self, schema):
        # `product(id: ID!)` is required
        result = validate_query(schema, "{ product { id } }")
        assert result["valid"] is False
        msgs = " ".join(e["message"] for e in result["errors"])
        assert "id" in msgs.lower() or "argument" in msgs.lower()


class TestVariableCoercion:
    def test_valid_variables_pass(self, schema):
        result = validate_query(
            schema,
            'query Get($id: ID!) { product(id: $id) { id } }',
            variables={"id": "gid://shopify/Product/1"},
        )
        assert result["valid"] is True
        assert result["coerced_variables"] == {"id": "gid://shopify/Product/1"}

    def test_missing_required_variable_fails(self, schema):
        result = validate_query(
            schema,
            'query Get($id: ID!) { product(id: $id) { id } }',
            variables={},
        )
        assert result["valid"] is False
        msgs = " ".join(e["message"] for e in result["errors"])
        assert "$id" in msgs or "id" in msgs.lower()

    def test_wrong_type_variable_fails(self, schema):
        # Pass an int where ProductInput is required.
        result = validate_query(
            schema,
            'mutation M($input: ProductInput!) { productCreate(input: $input) { product { id } } }',
            variables={"input": 42},
        )
        assert result["valid"] is False

    def test_valid_input_object_coerces(self, schema):
        result = validate_query(
            schema,
            'mutation M($input: ProductInput!) { productCreate(input: $input) { product { id } } }',
            variables={"input": {"title": "Test", "status": "DRAFT"}},
        )
        assert result["valid"] is True
        assert result["coerced_variables"]["input"]["title"] == "Test"


class TestOperationSelection:
    def test_operation_name_picks_right_op(self, schema):
        doc = """
            query A { shop { name } }
            query B($id: ID!) { product(id: $id) { id } }
        """
        # Selecting B without its required var should fail
        result = validate_query(schema, doc, variables={}, operation_name="B")
        assert result["valid"] is False

        # Selecting A doesn't need vars
        result = validate_query(schema, doc, operation_name="A")
        assert result["valid"] is True

    def test_ambiguous_op_without_name_returns_error(self, schema):
        doc = "query A { shop { name } } query B { shop { name } }"
        result = validate_query(schema, doc)
        assert result["valid"] is False
        msgs = " ".join(e["message"] for e in result["errors"])
        assert "operation_name" in msgs or "operation" in msgs.lower()
