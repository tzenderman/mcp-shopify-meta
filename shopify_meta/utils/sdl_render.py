"""Render an introspection type entry to a GraphQL SDL string.

Covers all the type kinds that appear in Shopify's Admin GraphQL schema:
OBJECT, INPUT_OBJECT, ENUM, INTERFACE, UNION, SCALAR. Output is valid SDL
that `graphql.parse` accepts.
"""

from __future__ import annotations


def render_type_ref(type_ref: dict) -> str:
    """Render a GraphQL type reference (introspection __Type) to SDL form.

    Handles NON_NULL and LIST wrappers recursively.
    """
    kind = type_ref.get("kind")
    if kind == "NON_NULL":
        return render_type_ref(type_ref["ofType"]) + "!"
    if kind == "LIST":
        return "[" + render_type_ref(type_ref["ofType"]) + "]"
    name = type_ref.get("name")
    if not name:
        raise ValueError(f"named type with no name: {type_ref!r}")
    return name


def _indent(text: str, n: int = 2) -> str:
    pad = " " * n
    return "\n".join(pad + line if line else line for line in text.splitlines())


def _render_description(description: str | None) -> str:
    if not description:
        return ""
    safe = description.replace('"""', '\\"\\"\\"')
    return f'"""\n{safe}\n"""\n'


def _render_arg(arg: dict) -> str:
    name = arg["name"]
    type_str = render_type_ref(arg["type"])
    default = arg.get("defaultValue")
    suffix = f" = {default}" if default is not None else ""
    return f"{name}: {type_str}{suffix}"


def _render_field(field: dict) -> str:
    name = field["name"]
    args = field.get("args") or []
    type_str = render_type_ref(field["type"])
    desc = _render_description(field.get("description"))

    if args:
        if len(args) == 1:
            args_block = "(" + _render_arg(args[0]) + ")"
        else:
            args_block = "(\n" + ",\n".join("  " + _render_arg(a) for a in args) + "\n  )"
        return f"{desc}{name}{args_block}: {type_str}"
    return f"{desc}{name}: {type_str}"


def _render_input_field(field: dict) -> str:
    name = field["name"]
    type_str = render_type_ref(field["type"])
    default = field.get("defaultValue")
    suffix = f" = {default}" if default is not None else ""
    desc = _render_description(field.get("description"))
    return f"{desc}{name}: {type_str}{suffix}"


def _render_enum_value(value: dict) -> str:
    name = value["name"]
    desc = _render_description(value.get("description"))
    return f"{desc}{name}"


def _render_object(entry: dict, keyword: str) -> str:
    name = entry["name"]
    desc = _render_description(entry.get("description"))
    interfaces = entry.get("interfaces") or []
    implements = ""
    if interfaces:
        implements = " implements " + " & ".join(i["name"] for i in interfaces)

    fields = entry.get("fields") or []
    if not fields:
        return f"{desc}{keyword} {name}{implements}".rstrip()

    body_parts = [_render_field(f) for f in fields]
    body = _indent("\n".join(body_parts))
    return f"{desc}{keyword} {name}{implements} {{\n{body}\n}}"


def _render_interface(entry: dict) -> str:
    return _render_object(entry, "interface")


def _render_input(entry: dict) -> str:
    name = entry["name"]
    desc = _render_description(entry.get("description"))
    fields = entry.get("inputFields") or []
    if not fields:
        return f"{desc}input {name}"
    body = _indent("\n".join(_render_input_field(f) for f in fields))
    return f"{desc}input {name} {{\n{body}\n}}"


def _render_enum(entry: dict) -> str:
    name = entry["name"]
    desc = _render_description(entry.get("description"))
    values = entry.get("enumValues") or []
    if not values:
        return f"{desc}enum {name}"
    body = _indent("\n".join(_render_enum_value(v) for v in values))
    return f"{desc}enum {name} {{\n{body}\n}}"


def _render_union(entry: dict) -> str:
    name = entry["name"]
    desc = _render_description(entry.get("description"))
    possible = entry.get("possibleTypes") or []
    members = " | ".join(t["name"] for t in possible)
    return f"{desc}union {name} = {members}" if members else f"{desc}union {name}"


def _render_scalar(entry: dict) -> str:
    name = entry["name"]
    desc = _render_description(entry.get("description"))
    return f"{desc}scalar {name}"


def render_type_definition(entry: dict | None) -> str:
    """Render a single introspection type entry as an SDL definition string."""
    if entry is None:
        raise ValueError("cannot render None as a type definition")
    kind = entry.get("kind")
    if kind == "OBJECT":
        return _render_object(entry, "type")
    if kind == "INTERFACE":
        return _render_interface(entry)
    if kind == "INPUT_OBJECT":
        return _render_input(entry)
    if kind == "ENUM":
        return _render_enum(entry)
    if kind == "UNION":
        return _render_union(entry)
    if kind == "SCALAR":
        return _render_scalar(entry)
    raise ValueError(f"unsupported type kind: {kind!r}")
