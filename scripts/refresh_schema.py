"""Refresh the vendored Shopify Admin GraphQL introspection JSON.

Usage:

    SHOPIFY_STORES='[{...}]' uv run python scripts/refresh_schema.py [--store NAME]

Writes (or overwrites) `shopify_meta/schema/admin_<version>.json`. Run this
once when setting up a new clone, and again any time you bump
`SHOPIFY_API_VERSION` or want to pick up new Shopify schema changes.

The script uses the same `GraphQLClient` and multi-store config as the rest
of the server, so credentials/URL/version semantics are identical.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from graphql import get_introspection_query

# Make `shopify_meta` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopify_meta.utils.graphql_client import DEFAULT_API_VERSION, get_graphql_client
from shopify_meta.utils.logging import setup_logging
from shopify_meta.utils.multi_store import get_store_manager

logger = logging.getLogger("refresh_schema")


def _output_path(version: str) -> Path:
    safe = version.replace("-", "_")
    return (
        Path(__file__).resolve().parent.parent
        / "shopify_meta"
        / "schema"
        / f"admin_{safe}.json"
    )


async def _fetch_schema(store_name: str | None) -> dict:
    manager = get_store_manager()
    if store_name is None:
        store_name = manager.list_stores()[0]
        logger.info("No --store given; using first configured store: %s", store_name)
    store_config = manager.get_store_config(store_name)

    client = get_graphql_client()
    query = get_introspection_query(descriptions=True)
    logger.info("Running introspection against %s", store_config["shopify_url"])
    body = await client.execute_query(store_config, query)
    if body.get("errors"):
        raise RuntimeError(f"introspection returned errors: {body['errors']}")
    if not body.get("data") or "__schema" not in body["data"]:
        raise RuntimeError(f"introspection response missing __schema: {body!r}")
    return body["data"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", help="Store name from SHOPIFY_STORES to use for introspection")
    args = parser.parse_args()

    load_dotenv()
    setup_logging()

    version = os.getenv("SHOPIFY_API_VERSION", DEFAULT_API_VERSION)
    out = _output_path(version)
    out.parent.mkdir(parents=True, exist_ok=True)

    data = asyncio.run(_fetch_schema(args.store))
    out.write_text(json.dumps(data, indent=2, sort_keys=True))
    logger.info("Wrote vendored schema to %s (%d bytes)", out, out.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
