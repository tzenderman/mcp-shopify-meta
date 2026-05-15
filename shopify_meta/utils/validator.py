"""GraphQL validator: parse + validate + coerce variables against a schema.

Returns a structured dict that never raises on user error — the model gets
clear feedback without exception traces leaking through the MCP layer.
"""

from __future__ import annotations

from typing import Any

from graphql import GraphQLError, GraphQLSchema, parse, validate
from graphql.execution.values import get_variable_values
from graphql.language.ast import OperationDefinitionNode


def _format_error(err: GraphQLError) -> dict:
    locations = None
    if err.locations:
        locations = [{"line": loc.line, "column": loc.column} for loc in err.locations]
    return {
        "message": err.message,
        "locations": locations,
        "path": list(err.path) if err.path else None,
    }


def _select_operation(
    document_ast, operation_name: str | None
) -> tuple[OperationDefinitionNode | None, list[dict]]:
    """Return (operation_node, errors). Either both set or one of them is empty/None."""
    ops = [d for d in document_ast.definitions if isinstance(d, OperationDefinitionNode)]
    if not ops:
        return None, [{"message": "document contains no executable operations", "locations": None, "path": None}]

    if operation_name:
        for op in ops:
            if op.name and op.name.value == operation_name:
                return op, []
        return None, [{
            "message": f"operation_name '{operation_name}' not found in document",
            "locations": None,
            "path": None,
        }]

    if len(ops) > 1:
        return None, [{
            "message": "document has multiple operations; specify operation_name to select one",
            "locations": None,
            "path": None,
        }]

    return ops[0], []


def validate_query(
    schema: GraphQLSchema,
    query: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
) -> dict:
    """Parse, validate, and coerce variables against the schema.

    Returns:
        {
            "valid": bool,
            "errors": [{"message", "locations", "path"}, ...],
            "coerced_variables": dict,
        }
    """
    variables = variables or {}

    try:
        document = parse(query)
    except GraphQLError as e:
        return {"valid": False, "errors": [_format_error(e)], "coerced_variables": {}}

    validation_errors = validate(schema, document)
    if validation_errors:
        return {
            "valid": False,
            "errors": [_format_error(e) for e in validation_errors],
            "coerced_variables": {},
        }

    operation, op_errors = _select_operation(document, operation_name)
    if op_errors:
        return {"valid": False, "errors": op_errors, "coerced_variables": {}}

    var_defs = list(operation.variable_definitions or [])
    coerced = get_variable_values(schema, var_defs, variables)
    if isinstance(coerced, list):
        return {
            "valid": False,
            "errors": [_format_error(e) for e in coerced],
            "coerced_variables": {},
        }

    return {"valid": True, "errors": [], "coerced_variables": coerced}
