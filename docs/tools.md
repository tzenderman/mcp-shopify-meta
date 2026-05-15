# Tools

This server exposes four MCP tools. The first three let the LLM walk Shopify's GraphQL schema at runtime; the fourth captures bug reports for the developer.

---

## `search_schema(keyword, kinds=None, limit=25)`

Find types and fields by keyword in Shopify's Admin GraphQL schema.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `keyword` | string | yes | Case-insensitive substring matched against type names, field names, enum values, and descriptions. |
| `kinds` | string[] | no | Restrict to one or more of: `Query`, `Mutation`, `Subscription`, `Object`, `Input`, `Enum`, `Interface`, `Union`, `Scalar`, `Field`, `EnumValue`. |
| `limit` | int | no | Default 25. Set higher to scan more matches. |

### Returns

```json
{
  "results": [
    {"name": "DraftOrder", "kind": "Object", "description": "...", "on_type": null},
    {"name": "draftOrderCreate", "kind": "Mutation", "description": "...", "on_type": "Mutation"}
  ],
  "total": 12,
  "truncated": false
}
```

Ranking, best first: exact name match → name prefix → name substring → description match. Within a tier, results are sorted alphabetically so output is stable.

### Examples

```python
search_schema("draftOrder")
search_schema("metafield", kinds=["Mutation"], limit=10)
search_schema("ACTIVE", kinds=["EnumValue"])
```

---

## `get_type_definition(type_name, depth=1)`

Return the GraphQL SDL definition for a single type plus its structured fields.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `type_name` | string | yes | Exact, case-sensitive type name (e.g. `DraftOrderInput`). |
| `depth` | int | no | `1` (default) returns just this type; `2` also inlines referenced object/input/enum/interface/union types one level deep. Capped at 2. Built-in scalars (`String`, `Int`, `Boolean`, `ID`, `Float`) are never inlined. |

### Returns

```json
{
  "name": "DraftOrder",
  "kind": "OBJECT",
  "description": "...",
  "sdl": "type DraftOrder { ... }",
  "fields": [
    {"name": "id", "description": null, "args": [], "type": {"kind": "NON_NULL", "name": null, "ofType": {"kind": "SCALAR", "name": "ID"}}, ...}
  ],
  "referenced_types": []
}
```

For input types, `input_fields` replaces `fields`. For enums, `enum_values` is provided. For interfaces and unions, `interfaces` / `possible_types` arrays are included.

### Examples

```python
get_type_definition("DraftOrderInput")
get_type_definition("DraftOrder", depth=2)  # also inlines DraftOrderLineItem, etc.
```

### Error handling

Unknown type returns `{"error": "Type 'X' not found...", "did_you_mean": "Y"}` with a closest-match suggestion. Never throws.

---

## `execute_graphql(query, store_name, variables=None, operation_name=None)`

Validate and execute a Shopify Admin GraphQL operation.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `query` | string | yes | GraphQL query or mutation document. |
| `store_name` | string | yes | Which configured store to target (must match a `store_name` from `SHOPIFY_STORES`). |
| `variables` | object | no | Variables for the operation. Types are coerced against the operation's declared variable types before sending. |
| `operation_name` | string | no | When the document defines multiple operations, names which one to execute. |

### Pipeline

The query is rejected before any network call if:
1. It doesn't **parse** as valid GraphQL syntax.
2. It doesn't **validate** against the vendored Shopify schema (unknown fields, wrong arg types, etc.).
3. Variables fail **coercion** (missing required, wrong type).

In all three cases, the response is `{"data": null, "errors": [{...}]}` with `message`, `locations`, and `path` populated.

### Returns

```json
{
  "data": {"shop": {"name": "..."}},
  "errors": [{"message": "..."}],          // present iff Shopify returned `errors`
  "cost": {                                 // present iff Shopify returned extensions.cost
    "requestedQueryCost": 5,
    "actualQueryCost": 4,
    "throttleStatus": {"maximumAvailable": 1000.0, "currentlyAvailable": 996.0, "restoreRate": 50.0}
  }
}
```

Use `cost.throttleStatus` to self-pace successive calls.

### Exceptions (transport-level)

These bubble up as `ToolError` to the MCP client — the model cannot fix them by adjusting the query:

- `ShopifyAuthError` — bad token (no retry)
- `ShopifyNotFoundError` — endpoint not found (no retry)
- `ShopifyRateLimitError` — 429s after exhausted retries
- `ShopifyAPIError` — 5xx after exhausted retries, network failures, JSON parse failures

### Examples

```python
execute_graphql(
    query="{ shop { name } }",
    store_name="main",
)

execute_graphql(
    query="""
        mutation Create($input: DraftOrderInput!) {
            draftOrderCreate(input: $input) {
                draftOrder { id }
                userErrors { field message }
            }
        }
    """,
    store_name="main",
    variables={"input": {"lineItems": [{"variantId": "gid://shopify/ProductVariant/1", "quantity": 1}]}},
)
```

---

## `report_issue(...)`

File a structured bug report when one of the other three tools doesn't behave as expected.

### Parameters

| Name | Type | Required | Description |
|---|---|:-:|---|
| `summary` | string | yes | One-line headline. |
| `tool_name` | string | yes | `search_schema`, `get_type_definition`, or `execute_graphql`. |
| `tool_arguments` | object | yes | Exact kwargs you passed. Enough for someone else to reproduce the call. |
| `observed_behavior` | string | yes | What actually happened. |
| `expected_behavior` | string | yes | What should have happened. |
| `severity` | string | no | `low`, `medium` (default), `high`. |
| `store_name` | string | no | Which configured store was targeted. |
| `error_message` | string | no | Exception class + message, if any. |
| `response_excerpt` | string | no | Truncated snippet of the response (auto-clipped to 2000 chars). |
| `client_context` | string | no | Model name, conversation topic, anything that helps repro. |

### Returns

```json
{
  "report_id": "rpt_a3f2c9d1",
  "stored_in_file": true,
  "stored_in_log": true,
  "thanks": "Issue rpt_a3f2c9d1 logged. The developer will review and follow up. ..."
}
```

### Storage

Each report is written to **two places** (so nothing is lost in either dev or prod):

1. `data/issue_reports.jsonl` (override path via `ISSUE_REPORT_PATH`). Append-only JSONL — one report per line.
2. A structured `ISSUE_REPORT <json>` log line at INFO level. Captured by Render's log stream (and any other stdout-capturing host) regardless of filesystem persistence.

If the file write fails (ephemeral filesystem, perms), `stored_in_file` returns `false` but the log line is still emitted and `report_id` is still returned — the report is never lost.

To review reports as a developer:

```bash
tail -n 20 data/issue_reports.jsonl | jq .            # local
grep "ISSUE_REPORT" /var/log/render-service.log       # production
```
