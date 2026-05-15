"""Tests for schema_loader: loading + indexing introspection JSON."""

import json

import pytest

from shopify_meta.utils.schema_loader import SchemaIndex, load_schema_from_dict, load_schema_from_path
from tests.fixtures.mini_schema import MINI_INTROSPECTION


class TestLoadFromDict:
    def test_loads_full_introspection(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        assert isinstance(idx, SchemaIndex)

    def test_query_type_name(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        assert idx.query_type == "QueryRoot"

    def test_mutation_type_name(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        assert idx.mutation_type == "Mutation"

    def test_subscription_type_none(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        assert idx.subscription_type is None

    def test_types_by_name_indexes_every_type(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        assert "Product" in idx.types_by_name
        assert "ProductInput" in idx.types_by_name
        assert "ProductStatus" in idx.types_by_name
        assert "Shop" in idx.types_by_name

    def test_types_by_name_preserves_introspection_shape(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        product = idx.types_by_name["Product"]
        assert product["kind"] == "OBJECT"
        field_names = {f["name"] for f in product["fields"]}
        assert {"id", "title", "status", "handle"} <= field_names

    def test_get_type_returns_entry_or_none(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        assert idx.get_type("Product")["name"] == "Product"
        assert idx.get_type("Nonexistent") is None


class TestSearchEntries:
    def test_includes_type_entries(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        kinds_by_name = {e.name: e.kind for e in idx.search_entries if e.on_type is None}
        assert kinds_by_name.get("Product") == "Object"
        assert kinds_by_name.get("ProductInput") == "Input"
        assert kinds_by_name.get("ProductStatus") == "Enum"
        assert kinds_by_name.get("ID") == "Scalar"

    def test_query_fields_get_query_kind(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        query_fields = [e for e in idx.search_entries if e.kind == "Query"]
        names = {e.name for e in query_fields}
        assert names == {"shop", "product", "products"}
        assert all(e.on_type == "QueryRoot" for e in query_fields)

    def test_mutation_fields_get_mutation_kind(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        mutation_fields = [e for e in idx.search_entries if e.kind == "Mutation"]
        names = {e.name for e in mutation_fields}
        assert names == {"productCreate", "productUpdate"}
        assert all(e.on_type == "Mutation" for e in mutation_fields)

    def test_object_fields_are_indexed_as_field(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        product_fields = [
            e for e in idx.search_entries if e.kind == "Field" and e.on_type == "Product"
        ]
        names = {e.name for e in product_fields}
        assert {"id", "title", "status", "handle"} <= names

    def test_enum_values_indexed_with_kind_enumvalue(self):
        idx = load_schema_from_dict(MINI_INTROSPECTION)
        values = [e for e in idx.search_entries if e.kind == "EnumValue"]
        names = {e.name for e in values}
        assert {"ACTIVE", "ARCHIVED", "DRAFT"} <= names
        assert all(e.on_type == "ProductStatus" for e in values if e.name in {"ACTIVE", "ARCHIVED", "DRAFT"})

    def test_introspection_meta_types_are_excluded(self):
        # Real introspection results include __Schema, __Type, etc.
        schema_with_meta = json.loads(json.dumps(MINI_INTROSPECTION))
        schema_with_meta["__schema"]["types"].append(
            {"kind": "OBJECT", "name": "__Type", "description": None, "fields": [], "inputFields": None, "interfaces": [], "enumValues": None, "possibleTypes": None}
        )
        idx = load_schema_from_dict(schema_with_meta)
        type_names = {e.name for e in idx.search_entries}
        assert "__Type" not in type_names


class TestLoadFromPath:
    def test_loads_valid_json_file(self, tmp_path):
        path = tmp_path / "schema.json"
        path.write_text(json.dumps(MINI_INTROSPECTION))
        idx = load_schema_from_path(str(path))
        assert idx.query_type == "QueryRoot"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="schema file"):
            load_schema_from_path(str(tmp_path / "missing.json"))

    def test_malformed_json_raises(self, tmp_path):
        path = tmp_path / "schema.json"
        path.write_text("{ not valid json !!")
        with pytest.raises(ValueError, match="malformed schema JSON"):
            load_schema_from_path(str(path))

    def test_missing_schema_key_raises(self, tmp_path):
        path = tmp_path / "schema.json"
        path.write_text(json.dumps({"oops": "wrong shape"}))
        with pytest.raises(ValueError, match="missing __schema"):
            load_schema_from_path(str(path))


class TestGetSchemaSingleton:
    def test_get_schema_caches(self, monkeypatch, tmp_path):
        path = tmp_path / "schema.json"
        path.write_text(json.dumps(MINI_INTROSPECTION))
        monkeypatch.setenv("SHOPIFY_SCHEMA_PATH", str(path))
        import shopify_meta.utils.schema_loader as mod

        mod._schema = None
        a = mod.get_schema()
        b = mod.get_schema()
        assert a is b
        mod._schema = None
