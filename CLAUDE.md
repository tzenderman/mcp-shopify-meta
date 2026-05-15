# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this server is

`mcp-shopify-meta` is the **schema-walking** counterpart to the sibling `mcp-shopify-admin` server. Instead of exposing one MCP tool per Shopify GraphQL operation, it exposes four generic tools:

- `search_schema(keyword, kinds, limit)` — keyword search across Shopify's GraphQL types/fields
- `get_type_definition(type_name, depth)` — returns SDL + structured form for a type
- `execute_graphql(query, store_name, variables, operation_name)` — parses, validates, then executes
- `report_issue(...)` — captures structured bug reports for later developer review

The model is expected to chain them: search → read schema → call. Read [docs/tools.md](docs/tools.md) for full signatures and examples.

## Schema source

The server validates and indexes against a **vendored** introspection JSON at `shopify_meta/schema/admin_<version>.json`. To refresh:

```bash
SHOPIFY_STORES='[...]' uv run python scripts/refresh_schema.py
```

See [docs/schema_refresh.md](docs/schema_refresh.md) for the workflow and when to refresh.

API version pin: `SHOPIFY_API_VERSION` env var (default `2024-10`). The vendored JSON's filename must match.

## ScaleKit Configuration

Identical setup to `mcp-shopify-admin`. Register your server in the ScaleKit dashboard:

1. **MCP Servers > Add MCP Server**
2. Server name: `shopify-meta`; Resource identifier: your server URL; Scopes: `shopify:read`, `shopify:write`
3. Enable dynamic client registration
4. Copy credentials to `.env`: `SCALEKIT_ENVIRONMENT_URL`, `SCALEKIT_CLIENT_ID`, `SCALEKIT_CLIENT_SECRET`, `SCALEKIT_RESOURCE_ID`

### Authentication Interceptors

Same email-allowlist pattern as the sibling repo. Two interceptors (`PRE_SIGNUP`, `PRE_SESSION_CREATION`) pointed at:
- `POST /auth/interceptors/pre-signup`
- `POST /auth/interceptors/pre-session-creation`

Set `SCALEKIT_INTERCEPTOR_SECRET` for signature verification, and `ALLOWED_EMAILS` for the allowlist (comma-separated; empty = allow all).

## Testing

### Running Tests

```bash
uv run pytest -v
uv run pytest --tb=short
uv run pytest tests/test_execute_graphql.py -v
```

### Test Structure

```
tests/
  conftest.py                       # mock_shopify context manager, mock_store_config, mini_schema fixtures
  fixtures/
    mini_schema.py                  # hand-rolled small introspection JSON for fast schema tests
    responses.py                    # MOCK_*_RESPONSE constants
  test_schema_loader.py             # load + index introspection JSON
  test_schema_search.py             # ranked substring search
  test_sdl_render.py                # introspection → SDL
  test_validator.py                 # parse / validate / coerce_variables
  test_search_schema.py             # MCP tool wrapper
  test_get_type_definition.py       # MCP tool wrapper (depth=1, depth=2)
  test_execute_graphql.py           # parse-reject, validate-reject, success, GraphQL errors, cost passthrough
  test_issue_reporter.py            # record_issue() unit tests
  test_report_issue.py              # MCP tool wrapper
  test_graphql_client.py            # ported retry/auth/error suite
  test_multi_store.py               # ported multi-store config
  test_session_store.py             # ported in-memory session TTL
  test_logging.py                   # truncate() + setup_logging() env reading
  test_server.py                    # EXPECTED_TOOLS = {"search_schema","get_type_definition","execute_graphql","report_issue"}
```

### TDD Workflow

This server follows strict TDD. Adding or changing a tool:

1. **Write the failing test first** in the relevant `tests/test_*.py` — assert the exact behavior you want.
2. **Run it; watch it fail** with `uv run pytest tests/test_<file>.py -v`.
3. **Write the minimal code** to make it pass.
4. **Run the full suite** — `uv run pytest -v` — to catch regressions.
5. **Refactor** while keeping the suite green.

Never write production code before its test exists and fails. Never adapt previously-written code; if you wrote code before the test, delete it.

### Test Patterns

**Schema-walking unit tests** use the small hand-rolled schema in `tests/fixtures/mini_schema.py` — fast, deterministic, no Shopify dependency.

**Contract tests** that exercise the real vendored Shopify schema live in the same test files as parametrized cases. Use them to assert "the `product` query exists with field X" — kept as a guardrail against vendored-schema drift.

**MCP tool tests** mock the GraphQL client (`mock_shopify` context manager from `conftest.py`) and assert the validator pipeline ran before any network call.

## Architecture

### Core components

**`shopify_meta/utils/graphql_client.py`** — async GraphQL client (ported verbatim from `mcp-shopify-admin`)
- Per-request `httpx.AsyncClient` (no persistent pool)
- Exponential backoff retry on 429/5xx and network/timeout failures (3 attempts, delays `[1s, 2s, 4s]`)
- Error hierarchy: `ShopifyAuthError`, `ShopifyNotFoundError`, `ShopifyRateLimitError`, `ShopifyAPIError`
- API version controlled by `SHOPIFY_API_VERSION` env (default `2024-10`)

**`shopify_meta/utils/schema_loader.py`** — module-import-time loader
- Reads `shopify_meta/schema/admin_<version>.json`
- Builds `types_by_name: dict[str, dict]` and `search_index: list[dict]`
- Fails loud at import if file missing/malformed

**`shopify_meta/utils/schema_search.py`** — ranked keyword search
- Substring match (case-insensitive) over names + descriptions
- Ranking: exact-name > prefix > substring > description
- Honors `kinds` filter and `limit`; returns `truncated` flag

**`shopify_meta/utils/sdl_render.py`** — introspection → SDL string
- Handles Object, Input, Enum, Interface, Union, Scalar
- Used by `get_type_definition`

**`shopify_meta/utils/validator.py`** — `graphql-core` pipeline
- `parse` → `validate` → `coerce_variable_values`
- Validation errors return structured `{path, locations, message}` — no exception leak

**`shopify_meta/utils/issue_reporter.py`** — single-function `record_issue(payload)`
- Always: structured `ISSUE_REPORT <json>` log line (captured by Render's log stream)
- Best-effort: append JSON to `data/issue_reports.jsonl` (configurable via `ISSUE_REPORT_PATH`)
- Returns `(report_id, wrote_to_file)`

**`shopify_meta/utils/multi_store.py`** — `SHOPIFY_STORES` JSON env var (ported)

**`shopify_meta/server.py`** — slim FastMCP registration (4 `mcp.tool()(fn)` calls)

**`shopify_meta/server_http.py`** — Starlette wrapper with ScaleKit OAuth + interceptors + session store (ported, package paths swapped)

**`shopify_meta/server_stdio.py`** — stdio entrypoint with env validation

## Common operations

### Search the schema

```python
search_schema("draftOrder")
# → list of types/fields with names containing "draftorder"

search_schema("metafield", kinds=["Mutation"], limit=10)
# → only mutations
```

### Inspect a type before composing a query

```python
get_type_definition("DraftOrderInput", depth=1)
# → SDL string + structured input fields
```

### Execute a composed query

```python
execute_graphql(
    query="""
        mutation Create($input: DraftOrderInput!) {
            draftOrderCreate(input: $input) { draftOrder { id } userErrors { message } }
        }
    """,
    variables={"input": {"lineItems": [{"variantId": "gid://shopify/ProductVariant/123", "quantity": 1}]}},
    store_name="main",
)
# Pipeline: parse → validate (against vendored schema) → coerce vars → POST
# Returns: {"data": ..., "cost": {requestedQueryCost, actualQueryCost, throttleStatus}}
```

### Report an issue when stuck

```python
report_issue(
    summary="draftOrderCreate succeeded but ignored my line item options",
    tool_name="execute_graphql",
    tool_arguments={"query": "mutation Create...", "variables": {...}, "store_name": "main"},
    observed_behavior="Returned a draft order with empty lineItems[0].options",
    expected_behavior="Should have preserved the options I passed",
    severity="medium",
)
# Appended to data/issue_reports.jsonl + logged with ISSUE_REPORT prefix.
```

## Development Notes

- The vendored introspection JSON is the canonical schema for both `get_type_definition` and `execute_graphql` validation. Stores can have schema extensions; we ignore them in v1.
- `execute_graphql` does NOT strip GIDs in responses — raw passthrough so the model can use IDs in follow-up calls.
- All issue reports include a generated `report_id` (`rpt_<hex8>`) — quote it back to the user when filing reports.
- Sensitive headers (`X-Shopify-Access-Token`, `Authorization`) are redacted in logs by the GraphQL client.
- MCP Streamable HTTP transport supports both batch and streaming response modes via FastMCP.
