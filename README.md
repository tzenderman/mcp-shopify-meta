# Shopify Admin Meta MCP Server

A Model Context Protocol (MCP) server for the [Shopify Admin GraphQL API](https://shopify.dev/docs/api/admin-graphql) that exposes **three generic tools** instead of one tool per operation. The model walks Shopify's schema at runtime: search → read type → execute.

## How it differs from `mcp-shopify-admin`

| | `mcp-shopify-admin` | `mcp-shopify-meta` (this repo) |
|---|---|---|
| Tool count | ~25 hand-curated (`search_products`, `create_draft_order`, …) | 4 generic (`search_schema`, `get_type_definition`, `execute_graphql`, `report_issue`) |
| Surface coverage | Only what's been curated | Full Shopify Admin GraphQL API |
| Best for | Common, well-known operations | Long-tail, novel, or rare-use queries |
| Context cost | High (tool list grows linearly) | Tiny (4 tools regardless of API size) |

Both servers can be installed in the same client; they're complementary.

## Tools

### `search_schema(keyword, kinds=None, limit=25)`
Find types and fields by keyword across Shopify's introspected schema.
```
search_schema("draftOrder") → [DraftOrder, DraftOrderInput, draftOrderCreate, …]
search_schema("metafield", kinds=["Mutation"]) → [metafieldsSet, metafieldDelete, …]
```

### `get_type_definition(type_name, depth=1)`
Return the GraphQL SDL definition for a type, plus structured field/arg info.
`depth=2` inlines referenced types one level deep (capped to prevent payload bloat).

### `execute_graphql(query, store_name, variables=None, operation_name=None)`
Parse, validate, and execute a GraphQL operation against a configured store.
- Syntax errors and validation errors are returned **without** making a network call.
- Returns `{"data": …, "errors"?: […], "cost"?: …}` — `cost` is Shopify's reported query cost for self-throttling.

### `report_issue(...)`
Capture a structured bug report whenever the model can't accomplish a task. Each report is appended to a JSONL file *and* logged as a structured line, so it persists in either local stdio mode or remote HTTP mode (where the filesystem is ephemeral).

Required fields: `summary`, `tool_name`, `tool_arguments`, `observed_behavior`, `expected_behavior`. Optional: `severity`, `store_name`, `error_message`, `response_excerpt`, `client_context`.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- A Shopify store with [Admin API access](https://shopify.dev/docs/api/admin-graphql)

## Setup

### Create a Shopify Admin API Token

1. **Settings > Apps and sales channels > Develop apps** in your Shopify admin
2. Create an app, enable the **Admin API scopes** you need
3. Install the app, copy the token (starts with `shpat_`)

### Install

```bash
uv venv
uv pip install -e .
```

### Vendor the GraphQL schema (one-time)

The server validates queries against a vendored introspection result. Refresh it from one of your stores:

```bash
SHOPIFY_STORES='[{...}]' uv run python scripts/refresh_schema.py
```

This writes `shopify_meta/schema/admin_<version>.json`. Re-run when bumping `SHOPIFY_API_VERSION` or when Shopify ships new types you want to expose.

### Stdio transport (Claude Desktop, local)

```json
{
  "mcpServers": {
    "shopify-meta": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-shopify-meta",
        "run", "python", "-m", "shopify_meta.server_stdio"
      ],
      "env": {
        "SHOPIFY_STORES": "[{\"store_name\":\"main\",\"shopify_url\":\"https://main.myshopify.com\",\"token\":\"shpat_xxx\"}]"
      }
    }
  }
}
```

### HTTP transport + ScaleKit OAuth (production)

```bash
uv run python -m shopify_meta.server_http
```

Required env: `SHOPIFY_STORES`, `SERVER_URL`, and the `SCALEKIT_*` set. See [CLAUDE.md](CLAUDE.md) for ScaleKit configuration.

## Running Tests

```bash
uv run pytest -v
```

## Architecture

- `shopify_meta/utils/graphql_client.py` — async HTTP client with retry, ported from `mcp-shopify-admin`
- `shopify_meta/utils/schema_loader.py` — loads the vendored introspection at import, builds in-memory indexes
- `shopify_meta/utils/validator.py` — wraps `graphql-core` parse + validate + variable coercion
- `shopify_meta/utils/issue_reporter.py` — single-function entry for `report_issue` storage
- `shopify_meta/resources/` — one module per tool group (`schema.py`, `execute.py`, `issues.py`)
- `shopify_meta/server.py` — FastMCP registration

See [CLAUDE.md](CLAUDE.md) for development patterns, test fixtures, and design rationale.

## Security

Do not commit `.env` or any tokens. Issue reports may contain query bodies and response excerpts — review `data/issue_reports.jsonl` before sharing.

## License

MIT
