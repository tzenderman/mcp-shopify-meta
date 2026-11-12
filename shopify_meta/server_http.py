"""HTTP transport entry point with ScaleKit OAuth 2.1 authentication."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastmcp.server.auth.providers.scalekit import ScalekitProvider
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from .server import create_mcp_server

load_dotenv()

logger = logging.getLogger("shopify_meta.http_server")

# ScaleKit Configuration. The email allowlist is enforced centrally by the
# standalone `scalekit-interceptor` service (the ScaleKit environment's
# interceptors point at it), so this server only validates OAuth tokens.
SCALEKIT_ENVIRONMENT_URL = os.getenv("SCALEKIT_ENVIRONMENT_URL")
SCALEKIT_RESOURCE_ID = os.getenv("SCALEKIT_RESOURCE_ID")
SERVER_URL = os.getenv("SERVER_URL")

def create_auth_provider() -> ScalekitProvider | None:
    """Create ScaleKit auth provider if configured."""
    required = [SCALEKIT_ENVIRONMENT_URL, SCALEKIT_RESOURCE_ID, SERVER_URL]
    if not all(required):
        logger.warning(
            "ScaleKit OAuth not configured. Set SCALEKIT_ENVIRONMENT_URL, "
            "SCALEKIT_RESOURCE_ID, and SERVER_URL environment variables."
        )
        return None

    return ScalekitProvider(
        environment_url=SCALEKIT_ENVIRONMENT_URL,
        resource_id=SCALEKIT_RESOURCE_ID,
        base_url=SERVER_URL,
    )


# Create auth provider and MCP server
auth_provider = create_auth_provider()
mcp = create_mcp_server(auth=auth_provider)


def create_app():
    """Create ASGI app with CORS middleware.

    Email-allowlist gating is handled centrally by the standalone
    `scalekit-interceptor` service, not here.
    """
    # Get the underlying Starlette app from FastMCP
    mcp_app = mcp.http_app()

    # Mount MCP app
    # IMPORTANT: Must pass mcp_app.lifespan to initialize FastMCP's session manager
    app = Starlette(
        routes=[
            Mount("/", app=mcp_app),  # Mount MCP app at root
        ],
        lifespan=mcp_app.lifespan,
    )

    # Add CORS middleware for MCP Inspector and browser clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    return app


# Create the ASGI app for uvicorn
app = create_app()


def main() -> None:
    """Run MCP server with HTTP transport and ScaleKit OAuth."""
    import uvicorn

    from .utils.schema_loader import get_schema

    # Validate required env vars
    required_vars = ["SHOPIFY_STORES"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    # Fail loud at startup if the vendored schema is missing or malformed.
    get_schema()

    if not auth_provider:
        logger.warning("Starting server WITHOUT OAuth authentication!")
    else:
        logger.info(f"ScaleKit environment: {SCALEKIT_ENVIRONMENT_URL}")
        logger.info(f"ScaleKit resource ID: {SCALEKIT_RESOURCE_ID}")

    logger.info("Email allowlist enforced centrally by the scalekit-interceptor service")

    port = int(os.getenv("PORT", "3000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting Shopify Admin Meta MCP Server on {host}:{port}")
    logger.info(f"Server URL: {SERVER_URL}")

    # Run with uvicorn directly using the CORS-wrapped app
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
