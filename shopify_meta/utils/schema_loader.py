"""Load and index a Shopify Admin GraphQL introspection JSON.

The result of an introspection query (see scripts/refresh_schema.py) is
expected to live at `shopify_meta/schema/admin_<version>.json`. This module
loads it lazily and builds in-memory indexes:

- `types_by_name`: name -> introspection type entry
- `search_entries`: flat list used by `search_schema` for ranked lookup

The default path can be overridden with the `SHOPIFY_SCHEMA_PATH` env var.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "2024-10"
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"

SCALAR_KIND_TO_SEARCH = {
    "OBJECT": "Object",
    "INPUT_OBJECT": "Input",
    "ENUM": "Enum",
    "INTERFACE": "Interface",
    "UNION": "Union",
    "SCALAR": "Scalar",
}


@dataclass(frozen=True)
class SearchEntry:
    """A single searchable element in the schema index."""

    name: str
    kind: str  # Query, Mutation, Subscription, Object, Input, Enum, Interface, Union, Scalar, Field, EnumValue
    description: str | None
    on_type: str | None = None  # for Field/Query/Mutation/Subscription/EnumValue


@dataclass(frozen=True)
class SchemaIndex:
    """Parsed + indexed introspection schema."""

    raw: dict
    types_by_name: dict[str, dict]
    search_entries: list[SearchEntry]
    query_type: str
    mutation_type: str | None
    subscription_type: str | None

    def get_type(self, name: str) -> dict | None:
        """Return the introspection entry for a type, or None if absent."""
        return self.types_by_name.get(name)


def _is_meta_type(name: str | None) -> bool:
    """Introspection meta-types (__Schema, __Type, etc.) start with two underscores."""
    return bool(name) and name.startswith("__")


def _categorize_root_field(parent_name: str, query_type: str, mutation_type: str | None, subscription_type: str | None) -> str:
    if parent_name == query_type:
        return "Query"
    if mutation_type and parent_name == mutation_type:
        return "Mutation"
    if subscription_type and parent_name == subscription_type:
        return "Subscription"
    return "Field"


def _build_search_entries(
    types: list[dict],
    query_type: str,
    mutation_type: str | None,
    subscription_type: str | None,
) -> list[SearchEntry]:
    entries: list[SearchEntry] = []
    root_types = {query_type, mutation_type, subscription_type}

    for t in types:
        name = t.get("name")
        if _is_meta_type(name):
            continue

        kind = t.get("kind")
        if name not in root_types:
            search_kind = SCALAR_KIND_TO_SEARCH.get(kind)
            if search_kind:
                entries.append(
                    SearchEntry(
                        name=name,
                        kind=search_kind,
                        description=t.get("description"),
                        on_type=None,
                    )
                )

        for f in t.get("fields") or []:
            entries.append(
                SearchEntry(
                    name=f["name"],
                    kind=_categorize_root_field(name, query_type, mutation_type, subscription_type),
                    description=f.get("description"),
                    on_type=name,
                )
            )

        for v in t.get("enumValues") or []:
            entries.append(
                SearchEntry(
                    name=v["name"],
                    kind="EnumValue",
                    description=v.get("description"),
                    on_type=name,
                )
            )

    return entries


def load_schema_from_dict(introspection: dict) -> SchemaIndex:
    """Build a SchemaIndex from an already-parsed introspection dict."""
    if "__schema" not in introspection:
        raise ValueError("introspection result is missing __schema key")

    schema_obj = introspection["__schema"]
    types = schema_obj.get("types") or []
    types_by_name = {t["name"]: t for t in types if t.get("name") and not _is_meta_type(t["name"])}

    query_type = (schema_obj.get("queryType") or {}).get("name")
    mutation_type = (schema_obj.get("mutationType") or {}).get("name")
    subscription_type = (schema_obj.get("subscriptionType") or {}).get("name")

    if not query_type:
        raise ValueError("introspection result has no queryType")

    entries = _build_search_entries(types, query_type, mutation_type, subscription_type)

    return SchemaIndex(
        raw=schema_obj,
        types_by_name=types_by_name,
        search_entries=entries,
        query_type=query_type,
        mutation_type=mutation_type,
        subscription_type=subscription_type,
    )


def load_schema_from_path(path: str) -> SchemaIndex:
    """Load + index introspection JSON from a filesystem path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"schema file not found at {path}")

    try:
        with open(p) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed schema JSON at {path}: {e}")

    if "__schema" not in data:
        raise ValueError(f"schema file at {path} is missing __schema key")

    return load_schema_from_dict(data)


def _default_schema_path() -> str:
    """Resolve the default vendored-schema path from SHOPIFY_API_VERSION."""
    version = os.getenv("SHOPIFY_API_VERSION", DEFAULT_API_VERSION).replace("-", "_")
    return str(SCHEMA_DIR / f"admin_{version}.json")


_schema: SchemaIndex | None = None
_graphql_schema = None


def get_schema() -> SchemaIndex:
    """Return the cached SchemaIndex, loading on first call.

    Reads `SHOPIFY_SCHEMA_PATH` env var if set, otherwise resolves
    the default `shopify_meta/schema/admin_<version>.json`.
    Fails loud if the file is missing or malformed.
    """
    global _schema
    if _schema is None:
        path = os.getenv("SHOPIFY_SCHEMA_PATH") or _default_schema_path()
        logger.info(f"Loading Shopify admin GraphQL schema from {path}")
        _schema = load_schema_from_path(path)
        logger.info(
            f"Schema loaded: {len(_schema.types_by_name)} types, "
            f"{len(_schema.search_entries)} search entries"
        )
    return _schema


def get_graphql_schema():
    """Return the cached graphql-core GraphQLSchema for validation."""
    global _graphql_schema
    if _graphql_schema is None:
        from graphql import build_client_schema  # local import to keep loader lightweight

        idx = get_schema()
        _graphql_schema = build_client_schema({"__schema": idx.raw})
    return _graphql_schema
