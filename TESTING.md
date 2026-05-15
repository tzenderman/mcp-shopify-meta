# Testing Guide

## Prerequisites

1. Shopify store with Admin API access token
2. `.env` file with `SHOPIFY_STORES` configured
3. Vendored introspection JSON present at `shopify_meta/schema/admin_<version>.json` (run `scripts/refresh_schema.py` once)

## Automated Tests

```bash
uv run pytest -v                                    # full suite
uv run pytest --tb=short                            # quick pass/fail
uv run pytest tests/test_execute_graphql.py -v      # one file
```

## Manual Testing Checklist

### `search_schema`
- [ ] Exact type match returns it first (e.g. `Product` ranks above `ProductInput`)
- [ ] Substring match across fields (e.g. `metafield` finds `metafieldsSet`, `metafield`, `MetafieldInput`)
- [ ] `kinds=["Mutation"]` filter restricts results
- [ ] `limit` honored, `truncated` flag set when results exceed limit
- [ ] Empty keyword returns a structured error, not a crash
- [ ] Unicode / special characters don't break the search

### `get_type_definition`
- [ ] `depth=1` returns the type's own fields/values only
- [ ] `depth=2` inlines referenced object/input/enum types
- [ ] `depth>2` is rejected or clamped
- [ ] Unknown type returns a structured error including a `did_you_mean` suggestion if close
- [ ] SDL string is parseable by `graphql.parse` (round-trip check)

### `execute_graphql`
- [ ] Valid query executes and returns `{data, cost}`
- [ ] Syntax error returns structured error, **no network call made**
- [ ] Validation error (unknown field) returns structured error, **no network call made**
- [ ] Variable type mismatch returns structured error, **no network call made**
- [ ] Shopify GraphQL errors (`{errors: [...]}`) bubble up under `errors` key
- [ ] `cost` field reflects Shopify's `extensions.cost`
- [ ] Missing `store_name` is rejected with a clear message
- [ ] Unknown `store_name` lists available stores in the error

### `report_issue`
- [ ] Missing required field (summary, tool_name, tool_arguments, observed, expected) is rejected
- [ ] Successful report returns `report_id` matching `rpt_[0-9a-f]{8}`
- [ ] JSONL file gets a new line with all fields + timestamp + server_version + python_version
- [ ] Same report appears in logs prefixed with `ISSUE_REPORT `
- [ ] If JSONL path is unwritable, response still returns `report_id` with `stored_in_file=False`; log line still emitted

### Multi-store
- [ ] `execute_graphql` with valid `store_name` works
- [ ] Invalid `store_name` lists available options
- [ ] Multiple stores in `SHOPIFY_STORES` are all usable

### Error handling
- [ ] Invalid token → `ShopifyAuthError`, no retry
- [ ] 429 → retried with `[1s, 2s, 4s]` backoff; final 429 raises `ShopifyRateLimitError`
- [ ] 5xx → retried; final 5xx raises `ShopifyAPIError`
- [ ] Timeout → retried; final timeout raises `ShopifyAPIError`

## Stdio Smoke Test

```bash
SHOPIFY_STORES='[{...}]' uv run python -m shopify_meta.server_stdio
# server boots, logs schema-load success, accepts MCP stdio handshake
```

## HTTP Smoke Test

1. Configure ScaleKit env vars + `SHOPIFY_STORES`
2. Start: `uv run python -m shopify_meta.server_http`
3. Connect with MCP Inspector: `npx @modelcontextprotocol/inspector http://localhost:3000/mcp`
4. Verify the 4 tools appear: `search_schema`, `get_type_definition`, `execute_graphql`, `report_issue`
5. Invoke each tool against a real store
