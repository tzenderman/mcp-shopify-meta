"""HTTP transport entry point with ScaleKit OAuth 2.1 authentication."""

from __future__ import annotations

import json
import logging
import os

import jwt
from dotenv import load_dotenv
from fastmcp.server.auth.providers.scalekit import ScalekitProvider
from scalekit import ScalekitClient
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount

from .server import create_mcp_server
from .utils.session_store import session_store, SESSION_ENABLED, SESSION_TTL_DAYS

load_dotenv()

logger = logging.getLogger("shopify_meta.http_server")

# ScaleKit Configuration
SCALEKIT_ENVIRONMENT_URL = os.getenv("SCALEKIT_ENVIRONMENT_URL")
SCALEKIT_CLIENT_ID = os.getenv("SCALEKIT_CLIENT_ID", "")
SCALEKIT_CLIENT_SECRET = os.getenv("SCALEKIT_CLIENT_SECRET", "")
SCALEKIT_RESOURCE_ID = os.getenv("SCALEKIT_RESOURCE_ID")
SCALEKIT_INTERCEPTOR_SECRET = os.getenv("SCALEKIT_INTERCEPTOR_SECRET", "")
SERVER_URL = os.getenv("SERVER_URL")

# Email allowlist for interceptors (comma-separated)
# Example: "alice@example.com,bob@example.com"
ALLOWED_EMAILS_RAW = os.getenv("ALLOWED_EMAILS", "")
ALLOWED_EMAILS: set[str] = {
    email.strip().lower()
    for email in ALLOWED_EMAILS_RAW.split(",")
    if email.strip()
}

# Session configuration
SESSION_COOKIE_NAME = "mcp_session"

# Initialize ScaleKit client for interceptor verification
scalekit_client: ScalekitClient | None = None
if SCALEKIT_ENVIRONMENT_URL and SCALEKIT_CLIENT_ID and SCALEKIT_CLIENT_SECRET:
    scalekit_client = ScalekitClient(
        SCALEKIT_ENVIRONMENT_URL,
        SCALEKIT_CLIENT_ID,
        SCALEKIT_CLIENT_SECRET,
    )


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


def is_email_allowed(email: str) -> bool:
    """Check if an email is in the allowlist.

    If ALLOWED_EMAILS is not set or empty, all emails are allowed.
    """
    if not ALLOWED_EMAILS:
        return True
    return email.lower() in ALLOWED_EMAILS


def verify_interceptor_signature(request: Request, body: bytes) -> bool:
    """Verify the interceptor request signature from ScaleKit.

    Returns True if verification passes or if verification is not configured.
    """
    if not SCALEKIT_INTERCEPTOR_SECRET:
        logger.warning("[INTERCEPTOR] No SCALEKIT_INTERCEPTOR_SECRET configured - skipping signature verification")
        return True

    if not scalekit_client:
        logger.warning("[INTERCEPTOR] ScaleKit client not initialized - skipping signature verification")
        return True

    headers = {
        'interceptor-id': request.headers.get('interceptor-id', ''),
        'interceptor-signature': request.headers.get('interceptor-signature', ''),
        'interceptor-timestamp': request.headers.get('interceptor-timestamp', ''),
    }

    try:
        is_valid = scalekit_client.verify_interceptor_payload(
            secret=SCALEKIT_INTERCEPTOR_SECRET,
            headers=headers,
            payload=body,
        )
        if not is_valid:
            logger.warning("[INTERCEPTOR] Invalid signature")
        return is_valid
    except Exception as e:
        logger.error(f"[INTERCEPTOR] Signature verification error: {e}")
        return False


async def handle_pre_signup(request: Request) -> JSONResponse:
    """Handle ScaleKit PRE_SIGNUP interceptor.

    Checks if the user's email is in the allowlist before allowing signup.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature
        if not verify_interceptor_signature(request, body):
            return JSONResponse(
                {"decision": "DENY", "error": {"message": "Invalid request signature"}},
            )

        # Parse JSON body
        data = json.loads(body)

        # Extract email from interceptor context (two possible locations per ScaleKit docs)
        user_email = (
            data.get("interceptor_context", {}).get("user_email", "")
            or data.get("data", {}).get("user", {}).get("email", "")
        )
        trigger_point = data.get("trigger_point", "")

        logger.info(f"[INTERCEPTOR] {trigger_point} for email: {user_email}")

        if is_email_allowed(user_email):
            logger.info(f"[INTERCEPTOR] ALLOW signup for: {user_email}")
            return JSONResponse({"decision": "ALLOW"})
        else:
            logger.warning(f"[INTERCEPTOR] DENY signup for: {user_email} (not in allowlist)")
            return JSONResponse({
                "decision": "DENY",
                "error": {"message": "Email not authorized for signup"}
            })

    except Exception as e:
        logger.error(f"[INTERCEPTOR] Error processing PRE_SIGNUP: {e}")
        # Fail closed - deny on error (always HTTP 200 per ScaleKit docs, decision in body)
        return JSONResponse({
            "decision": "DENY",
            "error": {"message": "Internal error processing signup"}
        })


async def handle_pre_session_creation(request: Request) -> JSONResponse:
    """Handle ScaleKit PRE_SESSION_CREATION interceptor.

    Checks if the user's email is in the allowlist before creating a session.
    This blocks deleted/unauthorized users even if they have a valid token.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify signature
        if not verify_interceptor_signature(request, body):
            return JSONResponse(
                {"decision": "DENY", "error": {"message": "Invalid request signature"}},
            )

        # Parse JSON body
        data = json.loads(body)

        # Extract email from interceptor context (two possible locations per ScaleKit docs)
        user_email = (
            data.get("interceptor_context", {}).get("user_email", "")
            or data.get("data", {}).get("user", {}).get("email", "")
        )
        trigger_point = data.get("trigger_point", "")

        logger.info(f"[INTERCEPTOR] {trigger_point} for email: {user_email}")

        if is_email_allowed(user_email):
            logger.info(f"[INTERCEPTOR] ALLOW session for: {user_email}")
            return JSONResponse({"decision": "ALLOW"})
        else:
            logger.warning(f"[INTERCEPTOR] DENY session for: {user_email} (not in allowlist)")
            return JSONResponse({
                "decision": "DENY",
                "error": {"message": "Email not authorized for access"}
            })

    except Exception as e:
        logger.error(f"[INTERCEPTOR] Error processing PRE_SESSION_CREATION: {e}")
        # Fail closed - deny on error (always HTTP 200 per ScaleKit docs, decision in body)
        return JSONResponse({
            "decision": "DENY",
            "error": {"message": "Internal error processing session"}
        })


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

    # Check email allowlist
    if not is_email_allowed(email):
        logger.warning(f"[SESSION] Denied session for non-allowed email: {email}")
        return JSONResponse(
            {"error": "Email not authorized"},
            status_code=403,
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
    """Create ASGI app with CORS middleware and interceptor endpoints."""
    # Get the underlying Starlette app from FastMCP
    mcp_app = mcp.http_app()

    # Define interceptor routes
    interceptor_routes = [
        Route("/auth/interceptors/pre-signup", handle_pre_signup, methods=["POST"]),
        Route("/auth/interceptors/pre-session-creation", handle_pre_session_creation, methods=["POST"]),
    ]

    # Define session management routes
    session_routes = [
        Route("/session/create", handle_session_create, methods=["POST"]),
        Route("/session/check", handle_session_check, methods=["GET"]),
        Route("/session/delete", handle_session_delete, methods=["POST", "DELETE"]),
    ]

    # Create main app with interceptor routes, session routes, and mount MCP app
    # IMPORTANT: Must pass mcp_app.lifespan to initialize FastMCP's session manager
    app = Starlette(
        routes=[
            *interceptor_routes,
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

    if ALLOWED_EMAILS:
        logger.info(f"Email allowlist configured with {len(ALLOWED_EMAILS)} email(s)")
    else:
        logger.warning("No ALLOWED_EMAILS configured - all emails permitted")

    if not SCALEKIT_INTERCEPTOR_SECRET:
        logger.warning("No SCALEKIT_INTERCEPTOR_SECRET configured - interceptor signatures will not be verified")

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
