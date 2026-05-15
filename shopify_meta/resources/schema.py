"""MCP tools that let the model walk the Shopify Admin GraphQL schema.

- `search_schema` — find types/fields by keyword.
- `get_type_definition` — return SDL + structured form for one type.

Both delegate to `utils.schema_loader` + `utils.schema_search` + `utils.sdl_render`.
"""

from __future__ import annotations

import logging
from typing import Any

from shopify_meta.utils.schema_loader import SchemaIndex, get_schema
from shopify_meta.utils.schema_search import search_schema_index
from shopify_meta.utils.sdl_render import render_type_definition

logger = logging.getLogger(__name__)

MAX_DEPTH = 2
BUILTIN_SCALARS = {"String", "Int", "Float", "Boolean", "ID"}


async def search_schema(
    keyword: str,
    kinds: list[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Search the Shopify Admin GraphQL schema by keyword.

    Args:
        keyword: Substring to match against type names, field names, enum values,
            and descriptions. Case-insensitive.
        kinds: Optional list of kinds to restrict results to. Valid values:
            "Query", "Mutation", "Subscription", "Object", "Input", "Enum",
            "Interface", "Union", "Scalar", "Field", "EnumValue".
        limit: Maximum number of results to return. Default 25.

    Returns:
        `{"results": [{"name","kind","description","on_type"}, ...],
          "total": int, "truncated": bool}`.
        On empty keyword, returns the same shape with an additional `error` key.
    """
    logger.debug("search_schema keyword=%r kinds=%r limit=%d", keyword, kinds, limit)

    try:
        result = search_schema_index(get_schema(), keyword=keyword, kinds=kinds, limit=limit)
        return result
    except ValueError as e:
        return {"results": [], "total": 0, "truncated": False, "error": str(e)}


def _collect_referenced_named_types(field_or_arg_type: dict, acc: set[str]) -> None:
    """Walk a type ref, accumulating named types encountered."""
    if not field_or_arg_type:
        return
    if field_or_arg_type.get("name"):
        acc.add(field_or_arg_type["name"])
    of_type = field_or_arg_type.get("ofType")
    if of_type:
        _collect_referenced_named_types(of_type, acc)


def _referenced_types(entry: dict) -> set[str]:
    """Return the set of named types referenced by an introspection type entry."""
    refs: set[str] = set()
    for f in entry.get("fields") or []:
        _collect_referenced_named_types(f.get("type"), refs)
        for a in f.get("args") or []:
            _collect_referenced_named_types(a.get("type"), refs)
    for f in entry.get("inputFields") or []:
        _collect_referenced_named_types(f.get("type"), refs)
    for i in entry.get("interfaces") or []:
        if i.get("name"):
            refs.add(i["name"])
    for p in entry.get("possibleTypes") or []:
        if p.get("name"):
            refs.add(p["name"])
    return refs


async def get_type_definition(
    type_name: str,
    depth: int = 1,
) -> dict[str, Any]:
    """Return the GraphQL SDL + structured form for a single type.

    Args:
        type_name: The exact (case-sensitive) name of the type.
        depth: 1 returns only this type's SDL; 2 also inlines referenced
            object/input/enum/interface/union types. Capped at 2.

    Returns:
        `{"name", "kind", "description", "sdl",
          "fields"|"input_fields"|"enum_values"|"interfaces"|"possible_types",
          "referenced_types"}`.
        On unknown type, returns `{"error": "..."}` with a `did_you_mean` hint
        if a close match exists.
    """
    schema: SchemaIndex = get_schema()
    entry = schema.get_type(type_name)
    if entry is None:
        suggestion = _suggest(schema, type_name)
        msg = f"Type '{type_name}' not found in schema."
        if suggestion:
            msg += f" Did you mean '{suggestion}'?"
        return {"error": msg, "did_you_mean": suggestion}

    capped_depth = max(1, min(depth, MAX_DEPTH))

    rendered_pieces = [render_type_definition(entry)]
    referenced: list[str] = []
    if capped_depth >= 2:
        for ref_name in sorted(_referenced_types(entry)):
            if ref_name == entry["name"] or ref_name in BUILTIN_SCALARS:
                continue
            ref_entry = schema.get_type(ref_name)
            if ref_entry is None:
                continue
            rendered_pieces.append(render_type_definition(ref_entry))
            referenced.append(ref_name)

    out: dict[str, Any] = {
        "name": entry["name"],
        "kind": entry["kind"],
        "description": entry.get("description"),
        "sdl": "\n\n".join(rendered_pieces),
        "referenced_types": referenced,
    }
    if entry.get("fields") is not None:
        out["fields"] = entry["fields"]
    if entry.get("inputFields") is not None:
        out["input_fields"] = entry["inputFields"]
    if entry.get("enumValues") is not None:
        out["enum_values"] = entry["enumValues"]
    if entry.get("interfaces"):
        out["interfaces"] = [i.get("name") for i in entry["interfaces"] if i.get("name")]
    if entry.get("possibleTypes"):
        out["possible_types"] = [p.get("name") for p in entry["possibleTypes"] if p.get("name")]
    return out


def _suggest(schema: SchemaIndex, type_name: str) -> str | None:
    """Best single suggestion for an unknown type name (case-insensitive equality first,
    then substring containment)."""
    lower = type_name.lower()
    names = list(schema.types_by_name.keys())
    for n in names:
        if n.lower() == lower:
            return n
    for n in names:
        if lower in n.lower() or n.lower() in lower:
            return n
    return None
