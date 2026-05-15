"""Stdio transport entry point for local usage (Claude Desktop, etc.)."""

import os
from pathlib import Path

from dotenv import load_dotenv

from .server import create_mcp_server
from .utils.schema_loader import get_schema


def main():
    """Run MCP server with stdio transport."""
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    load_dotenv(env_file)

    if not os.getenv("SHOPIFY_STORES"):
        raise RuntimeError(
            "SHOPIFY_STORES environment variable not set. "
            "Copy .env.example to .env and configure your stores."
        )

    # Fail loud at startup if the vendored schema is missing or malformed,
    # rather than silently failing every tool call.
    get_schema()

    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
