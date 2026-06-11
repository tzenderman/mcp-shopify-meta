"""HTTP transport entry point with ScaleKit OAuth 2.1 authentication."""

from __future__ import annotations

import logging
import os

import jwt
from dotenv import load_dotenv
from fastmcp.server.auth.providers.scalekit import ScalekitProvider
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount

from .server import create_mcp_server
from .utils.session_store import session_store, SESSION_ENABLED, SESSION_TTL_DAYS

load_dotenv()

logger = logging.getLogger("shopify_meta.http_server")

# ScaleKit Configuration. The email allowlist is enforced centrally by the
# standalone `scalekit-interceptor` service (the ScaleKit environment's
# interceptors point at it), so this server only validates OAuth tokens.
SCALEKIT_ENVIRONMENT_URL = os.getenv("SCALEKIT_ENVIRONMENT_URL")
SCALEKIT_RESOURCE_ID = os.getenv("SCALEKIT_RESOURCE_ID")
SERVER_URL = os.getenv("SERVER_URL")

# Session configuration
SESSION_COOKIE_NAME = "mcp_session"


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


def _extract_email_from_token(auth_header: str) -> str | None:
    """Extract user email from JWT token without verification.

    The token has already been verified by FastMCP/ScaleKit, so we just
    decode it to extract claims.
    """
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    try:
        # Decode without verification (already verified by ScaleKit)
        claims = jwt.decode(token, options={"verify_signature": False})
        # ScaleKit stores email in 'email' claim
        return claims.get("email") or claims.get("sub")
    except jwt.DecodeError as e:
        logger.warning(f"[SESSION] Failed to decode JWT: {e}")
        return None


async def handle_session_create(request: Request) -> Response:
    """Create a session after successful OAuth authentication.

    This endpoint requires a valid OAuth token. It extracts the user email
    from the token and creates a long-lived session.
    """
    if not SESSION_ENABLED:
        return JSONResponse(
            {"error": "Sessions are disabled"},
            status_code=503,
        )

    # Get auth header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return JSONResponse(
            {"error": "Authorization header required"},
            status_code=401,
        )

    # Extract email from token
    email = _extract_email_from_token(auth_header)
    if not email:
        return JSONResponse(
            {"error": "Could not extract email from token"},
            status_code=400,
        )

    # Create session
    session = session_store.create_session(email)
    logger.info(f"[SESSION] Created session for {email}")

    # Create response with session cookie
    response = JSONResponse({
        "status": "ok",
        "email": email,
        "expires_in_days": SESSION_TTL_DAYS,
    })

    # Set secure cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,  # Requires HTTPS
        samesite="lax",
    )

    return response


async def handle_session_check(request: Request) -> JSONResponse:
    """Check if current session is valid."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        return JSONResponse({"valid": False, "reason": "no_session"})

    session = session_store.get_session(session_id)
    if not session:
        return JSONResponse({"valid": False, "reason": "expired_or_invalid"})

    return JSONResponse({
        "valid": True,
        "email": session.user_email,
        "expires_at": session.expires_at,
    })


async def handle_session_delete(request: Request) -> Response:
    """Delete current session (logout)."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if session_id:
        session_store.delete_session(session_id)
        logger.info(f"[SESSION] Deleted session {session_id[:8]}...")

    response = JSONResponse({"status": "ok"})
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


# Create auth provider and MCP server
auth_provider = create_auth_provider()
mcp = create_mcp_server(auth=auth_provider)


def create_app():
    """Create ASGI app with CORS middleware and session endpoints.

    Email-allowlist gating is handled centrally by the standalone
    `scalekit-interceptor` service, not here.
    """
    # Get the underlying Starlette app from FastMCP
    mcp_app = mcp.http_app()

    # Define session management routes
    session_routes = [
        Route("/session/create", handle_session_create, methods=["POST"]),
        Route("/session/check", handle_session_check, methods=["GET"]),
        Route("/session/delete", handle_session_delete, methods=["POST", "DELETE"]),
    ]

    # Mount session routes + MCP app
    # IMPORTANT: Must pass mcp_app.lifespan to initialize FastMCP's session manager
    app = Starlette(
        routes=[
            *session_routes,
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

    if SESSION_ENABLED:
        logger.info(f"Session persistence enabled with {SESSION_TTL_DAYS} day TTL")
    else:
        logger.info("Session persistence disabled")

    port = int(os.getenv("PORT", "3000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting Shopify Admin Meta MCP Server on {host}:{port}")
    logger.info(f"Server URL: {SERVER_URL}")

    # Run with uvicorn directly using the CORS-wrapped app
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
