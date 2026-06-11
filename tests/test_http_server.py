"""Shape tests for the HTTP server after centralizing the email allowlist.

Gating now lives entirely in the standalone `scalekit-interceptor` service, so
this server keeps only ScaleKit OAuth (the `/mcp` gate) and the session
endpoints — the per-server interceptor endpoints and allowlist are removed.
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


def test_session_routes_retained():
    paths = _route_paths()
    assert "/session/create" in paths
    assert "/session/check" in paths
