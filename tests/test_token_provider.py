"""Tests for the token provider: static passthrough + client_credentials exchange."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shopify_meta.utils.errors import ShopifyAuthError
from shopify_meta.utils.token_provider import TokenProvider

STATIC_STORE = {
    "store_name": "static",
    "shopify_url": "https://static.myshopify.com",
    "token": "shpat_static",
}

CREDS_STORE = {
    "store_name": "creds",
    "shopify_url": "https://creds.myshopify.com",
    "client_id": "client-id-123",
    "client_secret": "client-secret-xyz",
}


class _Clock:
    """A controllable monotonic clock for cache-expiry tests."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _make_mock_response(status_code, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def _make_mock_client(post_return=None, post_side_effect=None):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    if post_side_effect is not None:
        mock_client.post = AsyncMock(side_effect=post_side_effect)
    else:
        mock_client.post = AsyncMock(return_value=post_return)
    return mock_client


@pytest.mark.asyncio
class TestTokenProvider:
    async def test_static_token_returned_without_http(self):
        """A store with a static token returns it directly, no HTTP exchange."""
        mock_client = _make_mock_client(post_return=_make_mock_response(200, {}))

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = TokenProvider()
            token = await provider.get_token(STATIC_STORE)

        assert token == "shpat_static"
        assert mock_client.post.await_count == 0

    async def test_exchange_client_credentials(self):
        """A credentials store exchanges client_id/secret at the oauth endpoint."""
        body = {"access_token": "shpat_minted", "scope": "read_orders", "expires_in": 86399}
        mock_client = _make_mock_client(post_return=_make_mock_response(200, body))

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = TokenProvider()
            token = await provider.get_token(CREDS_STORE)

        assert token == "shpat_minted"
        assert mock_client.post.await_count == 1
        called_url = mock_client.post.call_args[0][0]
        assert called_url == "https://creds.myshopify.com/admin/oauth/access_token"
        sent = mock_client.post.call_args.kwargs["data"]
        assert sent["grant_type"] == "client_credentials"
        assert sent["client_id"] == "client-id-123"
        assert sent["client_secret"] == "client-secret-xyz"

    async def test_token_cached_until_expiry(self):
        """A second call within the token's lifetime reuses the cached token."""
        body = {"access_token": "shpat_minted", "expires_in": 86399}
        mock_client = _make_mock_client(post_return=_make_mock_response(200, body))

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = TokenProvider(clock=_Clock(1000.0))
            t1 = await provider.get_token(CREDS_STORE)
            t2 = await provider.get_token(CREDS_STORE)

        assert t1 == t2 == "shpat_minted"
        assert mock_client.post.await_count == 1

    async def test_token_refetched_after_expiry(self):
        """Once the cached token expires, the next call re-exchanges."""
        body1 = {"access_token": "shpat_first", "expires_in": 100}
        body2 = {"access_token": "shpat_second", "expires_in": 100}
        mock_client = _make_mock_client(
            post_side_effect=[_make_mock_response(200, body1), _make_mock_response(200, body2)]
        )
        clock = _Clock(1000.0)

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = TokenProvider(clock=clock)
            t1 = await provider.get_token(CREDS_STORE)
            clock.t += 200  # past the 100s lifetime
            t2 = await provider.get_token(CREDS_STORE)

        assert t1 == "shpat_first"
        assert t2 == "shpat_second"
        assert mock_client.post.await_count == 2

    async def test_invalidate_forces_refetch(self):
        """invalidate() drops the cached token so the next call re-exchanges."""
        body1 = {"access_token": "shpat_first", "expires_in": 86399}
        body2 = {"access_token": "shpat_second", "expires_in": 86399}
        mock_client = _make_mock_client(
            post_side_effect=[_make_mock_response(200, body1), _make_mock_response(200, body2)]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = TokenProvider()
            t1 = await provider.get_token(CREDS_STORE)
            provider.invalidate("creds")
            t2 = await provider.get_token(CREDS_STORE)

        assert t1 == "shpat_first"
        assert t2 == "shpat_second"
        assert mock_client.post.await_count == 2

    async def test_exchange_failure_raises_auth_error(self):
        """A non-200 from the oauth endpoint raises ShopifyAuthError."""
        mock_client = _make_mock_client(
            post_return=_make_mock_response(401, text="invalid_client")
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = TokenProvider()
            with pytest.raises(ShopifyAuthError, match="client_credentials"):
                await provider.get_token(CREDS_STORE)
