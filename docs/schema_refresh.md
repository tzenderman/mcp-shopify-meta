# Refreshing the vendored GraphQL schema

The server validates and indexes against a single introspection JSON that ships with the repo at `shopify_meta/schema/admin_<version>.json`. It never queries the schema at runtime — refreshes are manual.

## When to refresh

- **Initial setup of a fresh clone** — the file is gitignored, so a new clone won't have one. The server fails loud at startup until you run the script.
- **Bumping `SHOPIFY_API_VERSION`** — each version has its own file (e.g. `admin_2024_10.json`, `admin_2025_01.json`).
- **Picking up new Shopify types/fields** — Shopify ships changes mid-version sometimes; rerun if you need them.

## Running the script

The script reuses the server's existing multi-store config, so the same `.env` works:

```bash
SHOPIFY_STORES='[{"store_name":"main","shopify_url":"https://main.myshopify.com","token":"shpat_xxx"}]' \
  uv run python scripts/refresh_schema.py
```

If you have multiple stores configured, pick one explicitly:

```bash
uv run python scripts/refresh_schema.py --store wholesale
```

Output:

```
INFO refresh_schema: Running introspection against https://main.myshopify.com
INFO refresh_schema: Wrote vendored schema to .../shopify_meta/schema/admin_2024_10.json (XXXXXX bytes)
```

## What the file contains

It's the verbatim result of `graphql.get_introspection_query(descriptions=True)` posted against Shopify, including every type, field, arg, enum value, and description Shopify exposes for that API version. Typical size: several MB. The server loads it once at startup and indexes it in memory; runtime cost is bounded by the index, not the file.

## Why we vendor it

- **Offline**: tests, validation, and `search_schema` work with no network round trip.
- **Deterministic**: a deploy that worked yesterday works today regardless of Shopify schema drift.
- **Verifiable**: schema diffs show up in git history when a new file is committed.
- **Fast**: no per-tool-call network cost for `search_schema` / `get_type_definition`.

## After refreshing

1. Inspect the diff (`git diff shopify_meta/schema/`) to see what changed.
2. Run the test suite: `uv run pytest -v`.
3. Commit the new file. (The path itself is git-tracked even though `.gitignore` excludes `data/issue_reports.jsonl`.)
