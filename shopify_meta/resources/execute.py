"""MCP tool: execute_graphql.

Pipeline:

1. Resolve store config (raises clear error if missing/unknown).
2. Parse the query string.
3. Validate it against the vendored Shopify schema.
4. Coerce supplied variables to the operation's declared types.
5. POST to Shopify via the shared `GraphQLClient`.
6. Return `{"data", "errors"?, "cost"?}` — `cost` mirrors Shopify's
   `extensions.cost` so the model can self-throttle.

Validation failures (1-4) never make a network call — the model gets the
error structure synchronously and can fix the query.
"""

from __future__ import annotations

import logging
from typing import Any

from shopify_meta.utils.errors import ShopifyError
from shopify_meta.utils.graphql_client import get_graphql_client
from shopify_meta.utils.multi_store import get_store_manager
from shopify_meta.utils.schema_loader import get_graphql_schema
from shopify_meta.utils.validator import validate_query

logger = logging.getLogger(__name__)


async def execute_graphql(
    query: str,
    store_name: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
) -> dict[str, Any]:
    """Validate, then execute, a Shopify Admin GraphQL operation.

    Args:
        query: A GraphQL query or mutation document.
        store_name: Which configured store to execute against. Required.
        variables: Variables for the operation. Optional.
        operation_name: Operation name when the document defines multiple.

    Returns:
        `{"data": ..., "errors"?: [...], "cost"?: {...}}` on success or when
        Shopify returns GraphQL semantic errors. On validation or store-config
        failure: `{"data": null, "errors": [{"message", "locations"?, "path"?}]}`.

    Raises:
        ShopifyAuthError | ShopifyRateLimitError | ShopifyAPIError:
            For transport-level failures the model cannot fix by adjusting the query
            (bad token, rate limit, 5xx exhausted, network failures).
    """
    logger.debug(
        "execute_graphql store=%s op=%s vars_count=%d",
        store_name,
        operation_name,
        len(variables or {}),
    )

    if not store_name:
        return {
            "data": None,
            "errors": [{"message": "store_name is required to execute a query."}],
        }

    try:
        store_config = get_store_manager().get_store_config(store_name)
    except ShopifyError as e:
        return {"data": None, "errors": [{"message": str(e)}]}

    schema = get_graphql_schema()
    validation = validate_query(
        schema, query, variables=variables, operation_name=operation_name
    )
    if not validation["valid"]:
        return {"data": None, "errors": validation["errors"]}

    coerced_variables = validation["coerced_variables"] or None

    client = get_graphql_client()
    body = await client.execute_query(
        store_config,
        query,
        variables=coerced_variables,
        operation_name=operation_name,
    )

    result: dict[str, Any] = {"data": body.get("data")}
    if body.get("errors"):
        result["errors"] = body["errors"]
    cost = (body.get("extensions") or {}).get("cost")
    if cost is not None:
        result["cost"] = cost
    return result
