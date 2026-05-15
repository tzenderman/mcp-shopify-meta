# Plan: `mcp-shopify-meta` — Generic Shopify Admin GraphQL MCP Server

## Context

The user already runs `mcp-shopify-admin`: a FastMCP server that ships ~25 hand-curated tools (`search_products`, `create_draft_order`, etc.) over Shopify's Admin GraphQL API. That model has two friction points: (1) the tool list grows linearly with Shopify's surface area, eating MCP client context; (2) anything outside the curated list (e.g. metafields, b2b, custom apps, new 2025+ types) is unreachable.

This new sibling server inverts the design: instead of one MCP tool per operation, the model walks Shopify's schema at runtime via three generic tools — search, lookup, execute — plus a `report_issue` tool so the LLM can flag bugs for later developer review. The result: tiny tool list, full API surface, and the model navigates the indirection (a pattern that's been shown to work well for large APIs like Stripe, Pipedream, and others).

This is a **new sibling repo**, parallel to the two existing servers under `/Users/timz/github/jean-paul/mcp-servers/`. The existing `mcp-shopify-admin/` is **not modified**. Conventions mirror both `mcp-shopify-admin/` and `mcp-cin7-core/` so the three repos stay consistent.

## Recommended Approach

### Repo & package

- Path: `/Users/timz/github/jean-paul/mcp-servers/mcp-shopify-meta/` (fresh `git init`)
- Python package: `shopify_meta` (matches the short-name convention of `shopify_server` / `cin7_core_server`)
- Python 3.10+; deps mirror `mcp-shopify-admin/pyproject.toml` exactly, plus `graphql-core>=3.2` for parse/validate
- Dev deps: `pytest>=9.0.2`, `pytest-asyncio>=1.3.0`
- Build backend: `hatchling`

### The four MCP tools

```python
# resources/schema.py
async def search_schema(
    keyword: str,
    kinds: list[str] | None = None,   # ["Query","Mutation","Object","Input","Enum","Interface","Union","Scalar"]
    limit: int = 25,
) -> dict
# Returns: {"results": [{"name","kind","description","on_type"?}], "total": int, "truncated": bool}
# Substring (case-insensitive) match against type names, field names, enum values, and descriptions.
# Ranking: exact-name first, prefix-name second, name-substring third, description match last.

async def get_type_definition(
    type_name: str,
    depth: int = 1,                   # capped at 2
) -> dict
# Returns: {"sdl": str, "name","kind","description","fields"|"enum_values"|"input_fields"|"possible_types","interfaces"}
# depth=1: just this type. depth=2: also inline referenced Object/Input/Enum types one level deep.

# resources/execute.py
async def execute_graphql(
    query: str,
    store_name: str,                  # required, no default (safety bias)
    variables: dict | None = None,
    operation_name: str | None = None,
) -> dict
# Pipeline before send: parse (graphql.parse) → validate (graphql.validate against vendored schema)
#                       → coerce variables (graphql.coerce_variable_values) → execute via GraphQLClient.
# Returns: {"data": ..., "errors"?: [...], "cost"?: {requestedQueryCost, actualQueryCost, throttleStatus}}
# Validation errors return as structured response (no exception leak): {"errors":[{"message","path","locations"}]}.
# Cost passthrough from Shopify's response.extensions.cost so the model can self-throttle.

# resources/issues.py
async def report_issue(
    summary: str,                     # required, one-line headline
    tool_name: Literal["search_schema","get_type_definition","execute_graphql"],
    tool_arguments: dict,             # required, exact kwargs the LLM tried
    observed_behavior: str,           # required, what happened
    expected_behavior: str,           # required, what should have happened
    severity: Literal["low","medium","high"] = "medium",
    store_name: str | None = None,
    error_message: str | None = None,
    response_excerpt: str | None = None,   # truncated to 2000 chars via utils.logging.truncate
    client_context: str | None = None,     # model name, conversation hint, etc.
) -> dict
# Returns: {"report_id": "rpt_<uuid8>", "stored_in_file": bool, "stored_in_log": True,
#           "thanks": "Issue logged. The developer will review and follow up."}
```

### `report_issue` storage — JSONL + structured log line

Chosen over Sentry / GitHub Issues / disk-only because:
- Local stdio mode: JSONL file is grep-able and persistent on the dev's laptop.
- Render HTTP mode: filesystem is ephemeral, but Render captures stdout indefinitely — the structured log line is the durable record.
- Same code path produces both sinks. No external dep, no DSN, no token, no rate limit, no moderation surface.
- Future-proof: a later `SENTRY_DSN` or Render Disk upgrade is a one-place change to `record_issue()`.

Implementation: `shopify_meta/utils/issue_reporter.py`

```python
def record_issue(payload: dict) -> tuple[str, bool]:
    """Returns (report_id, wrote_to_file). Always logs; file is best-effort."""
    report_id = "rpt_" + secrets.token_hex(4)
    payload = {
        "report_id": report_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "server": "mcp-shopify-meta",
        "server_version": __version__,
        "python_version": sys.version.split()[0],
        **payload,
    }
    # 1. Always: structured log line (Render captures this)
    logger.info("ISSUE_REPORT %s", json.dumps(payload))
    # 2. Best-effort: append to JSONL file (developer laptops, Render w/ Disk)
    path = os.getenv("ISSUE_REPORT_PATH", "./data/issue_reports.jsonl")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(payload) + "\n")
        return report_id, True
    except OSError as e:
        logger.warning("ISSUE_REPORT file write failed: %s", e)
        return report_id, False
```

### Schema source

- Vendor a single introspection JSON: `shopify_meta/schema/admin_2024_10.json`
- `scripts/refresh_schema.py` runs introspection against any configured store and rewrites the file. Run manually on API version bumps.
- `utils/schema_loader.py` loads + builds an in-memory index at module import:
  - `types_by_name: dict[str, GraphQLNamedType]`
  - `search_index: list[SearchEntry]` (tokenized for `search_schema`)
- Fail loud at import if file missing or malformed — mirror the `SHOPIFY_STORES` env-validation pattern.

### Files reused verbatim from `mcp-shopify-admin` (copy, don't import — repos stay independent)

- `utils/graphql_client.py` (per-request httpx, `[1.0, 2.0, 4.0]` retries on 429/5xx, error hierarchy)
- `utils/multi_store.py` (`SHOPIFY_STORES` JSON env, `StoreConfig` TypedDict, `MultiStoreManager`)
- `utils/errors.py` (`ShopifyError → AuthError / NotFoundError / RateLimitError / APIError`, carrying `store_name`)
- `utils/logging.py` (`setup_logging()` reading `MCP_LOG_LEVEL`/`MCP_LOG_FILE`, RotatingFileHandler 5MB×3, `truncate()`)
- `utils/session_store.py` (in-memory sessions, TTL via `SESSION_TTL_DAYS`)
- `server_stdio.py` shape: env validation → `create_mcp_server()` → `mcp.run(transport="stdio")`
- `server_http.py` shape: Starlette + ScaleKit OAuth + email allowlist interceptors + session routes, mounted at `/`
- `tests/conftest.py` `mock_shopify` context-manager pattern (per `tests/conftest.py:27-64` in sibling)
- `tests/test_server.py` `EXPECTED_TOOLS = {...}` assertion pattern
- `tests/test_graphql_client.py` retry/auth/error suite (`_make_mock_response` + `_make_mock_client`)
- `render.yaml` shape; `Procfile`: `web: python -m shopify_meta.server_http`

API version: `2024-10` (latest stable as of 2026-05). Override via `SHOPIFY_API_VERSION` env var.

### File layout

```
mcp-shopify-meta/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── TESTING.md
├── .env.example
├── .gitignore
├── render.yaml
├── Procfile
├── scripts/
│   └── refresh_schema.py            # one-shot introspection regen
├── shopify_meta/
│   ├── __init__.py                  # __version__
│   ├── server.py                    # FastMCP + 4 mcp.tool()(fn) registrations
│   ├── server_stdio.py              # env validation + stdio run
│   ├── server_http.py               # Starlette + ScaleKit + interceptors (ported)
│   ├── schema/
│   │   ├── __init__.py
│   │   └── admin_2024_10.json       # vendored introspection result
│   ├── resources/
│   │   ├── __init__.py
│   │   ├── schema.py                # search_schema, get_type_definition
│   │   ├── execute.py               # execute_graphql
│   │   └── issues.py                # report_issue
│   └── utils/
│       ├── __init__.py
│       ├── schema_loader.py         # load + index introspection JSON at import
│       ├── schema_search.py         # ranked substring search
│       ├── sdl_render.py            # introspection → SDL string
│       ├── validator.py             # parse + validate + coerce wrapper
│       ├── issue_reporter.py        # record_issue() (JSONL + log)
│       ├── graphql_client.py        # ported verbatim
│       ├── multi_store.py           # ported verbatim
│       ├── errors.py                # ported verbatim
│       ├── logging.py               # ported verbatim
│       └── session_store.py         # ported verbatim
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # mock_shopify + mini_schema fixture
│   ├── fixtures/
│   │   ├── __init__.py
│   │   ├── mini_schema.py           # hand-rolled small introspection JSON
│   │   └── responses.py             # MOCK_*_RESPONSE constants
│   ├── test_schema_loader.py
│   ├── test_schema_search.py        # ranking, kind filter, limit, truncated flag
│   ├── test_sdl_render.py
│   ├── test_validator.py            # parse errors, validation errors, var coercion, var coercion errors
│   ├── test_search_schema.py        # MCP tool tests for search_schema
│   ├── test_get_type_definition.py  # MCP tool tests; depth=1, depth=2, missing type
│   ├── test_execute_graphql.py      # parse-reject, validate-reject, success, GraphQL errors, cost passthrough
│   ├── test_report_issue.py         # required fields, JSONL append, file failure→log fallback, report_id shape
│   ├── test_issue_reporter.py       # unit tests for record_issue()
│   ├── test_graphql_client.py       # ported retry/auth/error suite
│   ├── test_multi_store.py          # ported
│   ├── test_session_store.py        # ported
│   ├── test_logging.py              # truncate() + setup_logging() env reading
│   └── test_server.py               # EXPECTED_TOOLS = {"search_schema","get_type_definition","execute_graphql","report_issue"}
└── docs/
    ├── tools.md                     # the 4 tools, signatures, examples
    └── schema_refresh.md            # how/when to run scripts/refresh_schema.py
```

### Critical files to be created (in execution order, TDD red→green→refactor per task)

1. `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `Procfile`, `render.yaml`, `CLAUDE.md`
2. `shopify_meta/__init__.py` (with `__version__`), `shopify_meta/utils/errors.py`, `shopify_meta/utils/logging.py` — ported
3. `shopify_meta/utils/multi_store.py`, `shopify_meta/utils/graphql_client.py`, `shopify_meta/utils/session_store.py` — ported (with tests ported)
4. `shopify_meta/schema/admin_2024_10.json` (initial vendored copy via `scripts/refresh_schema.py` against user's store)
5. `shopify_meta/utils/schema_loader.py` + `tests/fixtures/mini_schema.py` + `tests/test_schema_loader.py`
6. `shopify_meta/utils/schema_search.py` + `tests/test_schema_search.py`
7. `shopify_meta/utils/sdl_render.py` + `tests/test_sdl_render.py`
8. `shopify_meta/utils/validator.py` + `tests/test_validator.py`
9. `shopify_meta/utils/issue_reporter.py` + `tests/test_issue_reporter.py`
10. `shopify_meta/resources/schema.py` + `tests/test_search_schema.py` + `tests/test_get_type_definition.py`
11. `shopify_meta/resources/execute.py` + `tests/test_execute_graphql.py`
12. `shopify_meta/resources/issues.py` + `tests/test_report_issue.py`
13. `shopify_meta/server.py` + `tests/test_server.py`
14. `shopify_meta/server_stdio.py`, `shopify_meta/server_http.py`
15. `docs/tools.md`, `docs/schema_refresh.md`

### Reused functions/utilities (file:line in sibling repo to copy from)

- `mcp-shopify-admin/shopify_server/utils/graphql_client.py:17-145` — full GraphQLClient class
- `mcp-shopify-admin/shopify_server/utils/multi_store.py:1-115` — full MultiStoreManager + StoreConfig
- `mcp-shopify-admin/shopify_server/utils/errors.py:1-36` — full hierarchy
- `mcp-shopify-admin/shopify_server/utils/logging.py:1-49` — setup_logging + truncate
- `mcp-shopify-admin/shopify_server/utils/session_store.py:1-124` — full Session + SessionStore
- `mcp-shopify-admin/shopify_server/server_http.py:1-411` — Starlette + ScaleKit + interceptors (rename package only)
- `mcp-shopify-admin/tests/conftest.py:1-65` — adapt `mock_shopify` to patch `shopify_meta.utils` paths
- `mcp-shopify-admin/tests/test_graphql_client.py:1-150` — ported tests
- `mcp-shopify-admin/render.yaml` and `Procfile` — adapt service name + module path

### Env vars (.env.example)

```bash
# Required
SHOPIFY_STORES='[{"store_name":"main","shopify_url":"https://main.myshopify.com","token":"shpat_xxx"}]'

# Optional (with defaults)
SHOPIFY_API_VERSION=2024-10
ISSUE_REPORT_PATH=./data/issue_reports.jsonl
MCP_LOG_LEVEL=INFO
MCP_LOG_FILE=
SESSION_ENABLED=true
SESSION_TTL_DAYS=30
SERVER_URL=http://localhost:3000
HOST=0.0.0.0
PORT=3000

# Optional (HTTP transport + ScaleKit)
SCALEKIT_ENVIRONMENT_URL=
SCALEKIT_CLIENT_ID=
SCALEKIT_CLIENT_SECRET=
SCALEKIT_RESOURCE_ID=
SCALEKIT_INTERCEPTOR_SECRET=
ALLOWED_EMAILS=
```

### Explicit non-goals (YAGNI)

- No GID stripping / response projection / pagination helpers — the LLM writes the query; raw passthrough.
- No mutation gate / `MCP_ALLOW_MUTATIONS` env — sibling `mcp-shopify-admin` already permits mutations; matching that.
- No Sentry / GitHub Issues integration in v1 — `record_issue()` is the single extension point if added later.
- No live introspection per call — vendored schema + `scripts/refresh_schema.py` only.
- No fuzzy / semantic schema search — substring + ranked ordering for v1.
- No `depth > 2` in `get_type_definition` — payload explodes; cap and document.
- No per-store schemas — Shopify Admin API is uniform across stores; one schema file for all.

## Verification

End-to-end checks after implementation:

1. `cd /Users/timz/github/jean-paul/mcp-servers/mcp-shopify-meta && uv run pytest -v` — full suite passes
2. `uv run python -m shopify_meta.server_stdio` from a clean shell with `SHOPIFY_STORES` set — server boots, logs schema-load success, accepts MCP stdio handshake
3. `uv run python -c "from shopify_meta.server import create_mcp_server; import asyncio; print(asyncio.run(create_mcp_server().get_tools()).keys())"` — prints exactly `{"search_schema","get_type_definition","execute_graphql","report_issue"}`
4. Wire via `claude mcp add` to a local Claude Code session; manually exercise each tool:
   - `search_schema(keyword="draftOrder")` → finds `DraftOrder`, `draftOrderCreate`, etc.
   - `get_type_definition(type_name="DraftOrderInput")` → SDL string with all input fields
   - `execute_graphql(query="{ shop { name } }", store_name="<configured>")` → returns `{"data":{"shop":{"name":"..."}},"cost":{...}}`
   - `execute_graphql(query="{ shoq { name } }", store_name="<configured>")` → validation error (typo), no network call made
   - `report_issue(summary="...", tool_name="execute_graphql", tool_arguments={...}, observed_behavior="...", expected_behavior="...")` → returns `report_id`, appends a line to `data/issue_reports.jsonl`, logs `ISSUE_REPORT {...}`
5. `tail -1 data/issue_reports.jsonl | jq .` shows the captured payload with all fields
6. Render HTTP smoke test (after deploy): `curl https://<server>/mcp` returns the FastMCP handshake; log stream shows `ISSUE_REPORT` lines after a `report_issue` call

### Out-of-scope follow-ups (not blocking ship)

- CI workflow (GitHub Actions) for `pytest` on PR — copy from sibling repo when ready
- Auto-refresh schema via scheduled job
- Issue-report viewer CLI (`scripts/list_issues.py`)
