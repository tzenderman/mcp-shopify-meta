"""Tests for rendering an introspection type entry to GraphQL SDL."""

import pytest
from graphql import build_schema, parse

from shopify_meta.utils.schema_loader import load_schema_from_dict
from shopify_meta.utils.sdl_render import (
    render_type_definition,
    render_type_ref,
)
from tests.fixtures.mini_schema import MINI_INTROSPECTION


@pytest.fixture
def idx():
    return load_schema_from_dict(MINI_INTROSPECTION)


class TestRenderTypeRef:
    def test_named_scalar(self):
        ref = {"kind": "SCALAR", "name": "String", "ofType": None}
        assert render_type_ref(ref) == "String"

    def test_named_object(self):
        ref = {"kind": "OBJECT", "name": "Product", "ofType": None}
        assert render_type_ref(ref) == "Product"

    def test_non_null_wraps_with_bang(self):
        ref = {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None}}
        assert render_type_ref(ref) == "ID!"

    def test_list_wraps_with_brackets(self):
        ref = {"kind": "LIST", "name": None, "ofType": {"kind": "SCALAR", "name": "String", "ofType": None}}
        assert render_type_ref(ref) == "[String]"

    def test_non_null_list_of_non_null(self):
        ref = {
            "kind": "NON_NULL", "name": None,
            "ofType": {"kind": "LIST", "name": None,
                       "ofType": {"kind": "NON_NULL", "name": None,
                                  "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None}}},
        }
        assert render_type_ref(ref) == "[ID!]!"


class TestRenderObject:
    def test_object_with_fields(self, idx):
        sdl = render_type_definition(idx.get_type("Product"))
        assert "type Product {" in sdl
        assert "id: ID!" in sdl
        assert "title: String" in sdl
        assert "status: ProductStatus" in sdl

    def test_object_with_args(self, idx):
        sdl = render_type_definition(idx.get_type("QueryRoot"))
        assert "product(id: ID!): Product" in sdl
        assert "products(" in sdl
        assert "first: Int" in sdl
        assert "query: String" in sdl

    def test_object_description_emitted(self, idx):
        sdl = render_type_definition(idx.get_type("Shop"))
        assert '"""' in sdl  # description block syntax
        assert "A Shopify storefront." in sdl


class TestRenderInput:
    def test_input_type(self, idx):
        sdl = render_type_definition(idx.get_type("ProductInput"))
        assert "input ProductInput {" in sdl
        assert "title: String" in sdl
        assert "status: ProductStatus" in sdl


class TestRenderEnum:
    def test_enum_values(self, idx):
        sdl = render_type_definition(idx.get_type("ProductStatus"))
        assert "enum ProductStatus {" in sdl
        assert "ACTIVE" in sdl
        assert "ARCHIVED" in sdl
        assert "DRAFT" in sdl


class TestRenderScalar:
    def test_scalar_definition(self, idx):
        sdl = render_type_definition(idx.get_type("ID"))
        assert "scalar ID" in sdl
        # When a description is present, it precedes the declaration.
        assert "Global identifier." in sdl


class TestRoundTrip:
    def test_rendered_object_parses_as_valid_sdl(self, idx):
        """The rendered SDL is itself parseable GraphQL syntax."""
        sdl = render_type_definition(idx.get_type("Product"))
        # parse will raise if it's not valid SDL
        parse(sdl)

    def test_complete_minimal_schema_round_trips(self, idx):
        """Render every type into one document and build a schema from it."""
        types = [idx.get_type(n) for n in idx.types_by_name]
        rendered = "\n".join(render_type_definition(t) for t in types)
        # Add schema { query: ... } pointer so build_schema is happy.
        rendered += "\nschema { query: QueryRoot mutation: Mutation }\n"
        build_schema(rendered)


class TestUnknownType:
    def test_none_input_raises(self):
        with pytest.raises(ValueError, match="cannot render None"):
            render_type_definition(None)

    def test_unsupported_kind_raises(self):
        with pytest.raises(ValueError, match="unsupported"):
            render_type_definition({"kind": "WEIRD", "name": "X"})
