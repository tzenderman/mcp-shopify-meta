"""Shape tests for the HTTP server after centralizing the email allowlist.

Gating now lives entirely in the standalone `scalekit-interceptor` service, so
this server keeps only ScaleKit OAuth (the `/mcp` gate) — the per-server
interceptor endpoints, allowlist and session endpoints are removed.
"""

import shopify_meta.server_http as srv


def _route_paths():
    return [getattr(r, "path", "") for r in srv.app.routes]


def test_interceptor_routes_removed():
    assert not any("interceptor" in p for p in _route_paths()), _route_paths()


def test_interceptor_and_allowlist_symbols_removed():
    for name in (
        "handle_pre_signup",
        "handle_pre_session_creation",
        "verify_interceptor_signature",
        "is_email_allowed",
        "scalekit_client",
        "ALLOWED_EMAILS",
    ):
        assert not hasattr(srv, name), f"{name} should be removed (centralized in scalekit-interceptor)"


def test_oauth_provider_retained():
    assert hasattr(srv, "create_auth_provider")
    assert srv.SCALEKIT_RESOURCE_ID is None or isinstance(srv.SCALEKIT_RESOURCE_ID, str)


def test_session_routes_removed():
    """The /session/* endpoints minted cookies from an UNVERIFIED JWT and no
    route ever accepted that cookie as auth — dead code with a forgery hole.
    The MCP endpoint is gated by ScaleKit bearer tokens alone."""
    assert not any(p.startswith("/session") for p in _route_paths()), _route_paths()


def test_session_symbols_removed():
    for name in (
        "handle_session_create",
        "handle_session_check",
        "handle_session_delete",
        "_extract_email_from_token",
        "SESSION_COOKIE_NAME",
        "session_store",
    ):
        assert not hasattr(srv, name), f"{name} should be removed"


# --- Fail closed when OAuth is not configured --------------------------------

import pytest


@pytest.fixture
def fake_uvicorn(monkeypatch):
    """Capture uvicorn.run instead of binding a port."""
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setenv("SHOPIFY_STORES", '[{"store_name":"s","shopify_url":"https://s.myshopify.com","token":"t"}]')
    return calls


def test_main_refuses_to_start_without_oauth(monkeypatch, fake_uvicorn):
    monkeypatch.setattr(srv, "auth_provider", None)
    monkeypatch.delenv("MCP_ALLOW_NO_AUTH", raising=False)

    with pytest.raises(RuntimeError, match="SCALEKIT"):
        srv.main()

    assert fake_uvicorn == [], "server must not start without OAuth"


def test_main_starts_without_oauth_only_with_explicit_opt_out(monkeypatch, fake_uvicorn):
    monkeypatch.setattr(srv, "auth_provider", None)
    monkeypatch.setenv("MCP_ALLOW_NO_AUTH", "1")

    srv.main()

    assert len(fake_uvicorn) == 1


def test_main_starts_with_oauth(monkeypatch, fake_uvicorn):
    monkeypatch.setattr(srv, "auth_provider", object())
    monkeypatch.delenv("MCP_ALLOW_NO_AUTH", raising=False)

    srv.main()

    assert len(fake_uvicorn) == 1
