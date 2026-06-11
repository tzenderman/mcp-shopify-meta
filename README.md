# Shopify Admin Meta MCP Server

This is a Model Context Protocol (MCP) server for the [Shopify Admin API](https://shopify.dev/docs/api/admin-graphql). Instead of exposing one tool per Shopify GraphQL operation, this server exposes **three generic schema-walking tools** plus a structured bug-report tool. The model finds what it needs at runtime: search the schema → read a type definition → execute the composed query.

It's a sibling to [`mcp-shopify-admin`](../mcp-shopify-admin) — that server ships ~25 hand-curated tools (`search_products`, `create_draft_order`, …) for common operations. This one covers the **full** Admin GraphQL surface (metafields, b2b, custom apps, anything Shopify ships) with a tiny tool list that doesn't grow as the API grows. Both servers can be installed in the same client; they're complementary.

## Features

- Four MCP tools that cover the full Shopify Admin GraphQL surface
- Schema-walking pattern (`search → describe → execute`) keeps the tool list tiny
- Query validation against a vendored Shopify schema — syntax, validation, and variable-coercion errors are caught **before** any network call
- Cost passthrough — Shopify's `extensions.cost` is surfaced so the model can self-throttle
- Structured bug-report tool with dual JSONL + log persistence
- Multi-store support
- ScaleKit OAuth 2.0 / Streamable HTTP transport for remote deployments
- Stdio transport for local Claude Desktop integration
- MCP protocol compliance

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- A Shopify store with [Admin API access](https://shopify.dev/docs/api/admin-graphql) (custom app with API token)

## Docs and Links

- [Shopify Admin GraphQL API Reference](https://shopify.dev/docs/api/admin-graphql)
- [Shopify Admin API Authentication](https://shopify.dev/docs/api/admin-graphql#authentication)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [`docs/tools.md`](docs/tools.md) — full reference for the four MCP tools
- [`docs/schema_refresh.md`](docs/schema_refresh.md) — how/when to refresh the vendored schema

## Setup

### Create a Shopify Admin API Token

1. In your Shopify admin, go to **Settings > Apps and sales channels > Develop apps**
2. Create a new app and configure the **Admin API scopes** you need (e.g., `read_products`, `write_products`, `read_orders`, `write_orders`, etc.)
3. Install the app and copy the **Admin API access token** (starts with `shpat_`)

### Authentication

There are 2 modes of running the Shopify Admin Meta MCP server:

#### 1. Streamable HTTP with OAuth (Recommended for production)

This mode runs the server as a web service with OAuth 2.0 authentication via [ScaleKit](https://scalekit.com/). This is the recommended approach for shared or remote deployments, including connecting via Claude Desktop's remote MCP connector.

**Required environment variables:**
- `SHOPIFY_STORES` - JSON array of store configurations (see below)
- `SCALEKIT_ENVIRONMENT_URL` - ScaleKit environment URL (e.g., `https://yourapp.scalekit.com`)
- `SCALEKIT_CLIENT_ID` - ScaleKit application client ID
- `SCALEKIT_CLIENT_SECRET` - ScaleKit application client secret
- `SCALEKIT_RESOURCE_ID` - ScaleKit resource identifier (e.g., `res_xxx`)
- `SCALEKIT_INTERCEPTOR_SECRET` - Secret for verifying interceptor payloads
- `SERVER_URL` - Your MCP server's public URL (e.g., `https://your-server.example.com`)

**Optional:**
- `ALLOWED_EMAILS` - Comma-separated list of allowed email addresses (leave empty to allow all authenticated users)
- `SHOPIFY_API_VERSION` - Pinned API version (default `2024-10`)
- `ISSUE_REPORT_PATH` - Where `report_issue` writes its JSONL file (default `./data/issue_reports.jsonl`)
- `MCP_LOG_LEVEL` - Logging level (default `INFO`)
- `MCP_LOG_FILE` - Enable file logging with rotation

**Store configuration:**
```bash
SHOPIFY_STORES='[
  {
    "store_name": "my-store",
    "shopify_url": "https://my-store.myshopify.com",
    "token": "shpat_xxxxx"
  }
]'
```

Multiple stores are supported — add additional objects to the array.

**Running the server:**
```bash
uv run python -m shopify_meta.server_http
```

**Endpoints:**
- `GET /health` - Health check (no auth required)
- `GET /.well-known/oauth-protected-resource` - OAuth discovery (no auth required)
- `POST /mcp` - MCP endpoint (requires OAuth 2.0 Bearer token)

**Connecting from Claude Desktop (remote):**
1. Deploy your server (e.g., to Render — see [`render.yaml`](render.yaml))
2. Open **Claude Desktop** > **Settings** > **Connectors**
3. Click **"Add Connector"** and enter your server URL: `https://your-server.com/mcp`
4. Claude will auto-discover OAuth configuration
5. Click **"Authorize"** and log in

See [CLAUDE.md](CLAUDE.md) for detailed ScaleKit setup and interceptor configuration.

#### 2. Stdio Transport (Local development)

This mode runs the server locally using stdio transport for direct integration with Claude Desktop. No OAuth configuration needed — Shopify credentials are used directly.

**Required environment variables:**
- `SHOPIFY_STORES` - JSON array of store configurations (see above)

**Optional:** `SHOPIFY_API_VERSION`, `ISSUE_REPORT_PATH`, `MCP_LOG_LEVEL`, `MCP_LOG_FILE`.

**Claude Desktop configuration:**

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "shopify-meta": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-shopify-meta",
        "run",
        "python",
        "-m",
        "shopify_meta.server_stdio"
      ],
      "env": {
        "SHOPIFY_STORES": "[{\"store_name\":\"my-store\",\"shopify_url\":\"https://my-store.myshopify.com\",\"token\":\"shpat_xxx\"}]"
      }
    }
  }
}
```

Replace `/absolute/path/to/mcp-shopify-meta` with the actual path to your clone of this repository.

If you're running both servers together, give them distinct names (e.g. `shopify-admin` for the curated server and `shopify-meta` for this one) so Claude lists their tools separately.

### Installation

```bash
# Create virtual environment and install dependencies
uv venv
uv pip install -e .

# Quick import check
uv run python -c "import shopify_meta.server; print('OK')"
```

### Vendor the GraphQL schema (one-time)

This server validates queries against a vendored introspection result that ships at `shopify_meta/schema/admin_<version>.json`. A fresh clone won't have one — generate it from any store you've configured:

```bash
SHOPIFY_STORES='[{...}]' uv run python scripts/refresh_schema.py
```

Re-run whenever you bump `SHOPIFY_API_VERSION` or want to pick up new Shopify schema changes. See [`docs/schema_refresh.md`](docs/schema_refresh.md) for the full workflow.

### Testing with MCP Inspector

```bash
# Start the HTTP server
uv run python -m shopify_meta.server_http

# In another terminal, open MCP Inspector
npx @modelcontextprotocol/inspector http://localhost:3000/mcp
```

## Available MCP Tools

**Schema walking:**
- `search_schema(keyword, kinds, limit)` — Ranked keyword search across types, fields, enum values, and descriptions. Returns `{"results": [...], "total": int, "truncated": bool}`.
- `get_type_definition(type_name, depth)` — Return the GraphQL SDL for one type, plus structured field/arg info. `depth=2` inlines referenced types one level deep (capped at 2).

**Execution:**
- `execute_graphql(query, store_name, variables, operation_name)` — Parse, validate, and execute a GraphQL query or mutation against a configured store. Validation errors (syntax, unknown field, wrong variable type) are returned **without** a network call. Returns `{"data": ..., "errors"?: [...], "cost"?: {...}}` — `cost` mirrors Shopify's `extensions.cost` for self-throttling.

**Issue reporting:**
- `report_issue(summary, tool_name, tool_arguments, observed_behavior, expected_behavior, ...)` — File a structured bug report when a tool doesn't behave as expected. Each report is appended to `data/issue_reports.jsonl` *and* emitted as an `ISSUE_REPORT <json>` log line, so reports survive even on hosts with ephemeral filesystems. Returns a `report_id` the model can quote in follow-ups.

For detailed signatures, examples, and return shapes, see [`docs/tools.md`](docs/tools.md).

For the underlying Shopify Admin GraphQL API documentation, refer to the [Shopify Admin GraphQL API Reference](https://shopify.dev/docs/api/admin-graphql).

## For Developers

### Running Tests

```bash
# Full test suite
uv run pytest -v

# Quick pass/fail check
uv run pytest --tb=short

# Specific test file
uv run pytest tests/test_execute_graphql.py -v
```

### Contributing — Test-Driven Development

This project follows a strict **test-driven development (TDD)** workflow. Every utility and tool was implemented test-first:

1. **Add fixtures** to `tests/fixtures/` — either using the small hand-rolled `mini_schema.py` (fast, deterministic) or real `<ACTION>_<QUALIFIER>_RESPONSE` constants from the [Shopify Admin GraphQL API docs](https://shopify.dev/docs/api/admin-graphql)
2. **Write failing tests** — unit tests against the mini schema, contract tests against the real vendored schema where relevant
3. **Implement** to make the tests pass

No new code should be merged without corresponding test coverage. See [CLAUDE.md](CLAUDE.md) for detailed test patterns, the `mock_shopify` fixture, and the `EXPECTED_TOOLS` registration assertion.

### Architecture

- **`graphql_client.py`** - Async GraphQL client for the Shopify Admin API with retry and error handling (ported from `mcp-shopify-admin`)
- **`schema_loader.py`** - Loads the vendored introspection JSON at startup, builds the in-memory type and search indexes, exposes the parsed `GraphQLSchema` for validation
- **`schema_search.py`** - Ranked substring search over the schema index (exact > prefix > substring > description)
- **`sdl_render.py`** - Renders introspection type entries back to SDL strings (Object, Input, Enum, Interface, Union, Scalar)
- **`validator.py`** - Wraps `graphql-core` for parse + validate + variable coercion; returns structured error responses instead of raising
- **`issue_reporter.py`** - Single-function entry point for `report_issue` storage (JSONL append + structured log line)
- **`multi_store.py`** - `SHOPIFY_STORES` JSON-env multi-tenant config (ported)
- **`session_store.py`** - In-memory session storage with TTL (ported)
- **`server.py`** - FastMCP server with the four tool registrations
- **`server_http.py`** - Starlette wrapper with MCP Streamable HTTP transport and ScaleKit OAuth (ported)
- **`server_stdio.py`** - Stdio transport for local Claude Desktop integration
- **`resources/`** - Tool implementations (`schema.py`, `execute.py`, `issues.py`)
- **`utils/`** - Shared utilities

See [CLAUDE.md](CLAUDE.md) for comprehensive development documentation, test patterns, and architecture details.

## Security

Do not commit your `.env` file or any Shopify API tokens to version control (it is included in `.gitignore` as a safe default).

Issue reports written by `report_issue` may contain raw query bodies, variables, and response excerpts — review `data/issue_reports.jsonl` before sharing it with anyone outside the project.

## License

MIT
