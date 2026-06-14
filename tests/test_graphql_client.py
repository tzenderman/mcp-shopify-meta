"""Tests for GraphQL client with retry logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shopify_meta.utils.errors import (
    ShopifyAPIError,
    ShopifyAuthError,
    ShopifyNotFoundError,
    ShopifyRateLimitError,
)
from shopify_meta.utils.graphql_client import GraphQLClient

STORE_CONFIG = {
    "store_name": "test",
    "shopify_url": "https://test.myshopify.com",
    "token": "tok",
}


def _make_mock_response(status_code, json_data=None, text=""):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def _make_mock_client(post_return=None, post_side_effect=None):
    """Create a mock httpx.AsyncClient as an async context manager."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    if post_side_effect is not None:
        mock_client.post = AsyncMock(side_effect=post_side_effect)
    else:
        mock_client.post = AsyncMock(return_value=post_return)
    return mock_client


CREDS_CONFIG = {
    "store_name": "creds",
    "shopify_url": "https://creds.myshopify.com",
    "client_id": "cid",
    "client_secret": "csecret",
}


class _SeqProvider:
    """Fake TokenProvider returning a fresh token per call, recording invalidations."""

    def __init__(self, *tokens):
        self.tokens = list(tokens)
        self.invalidated = []

    async def get_token(self, store_config):
        return self.tokens.pop(0)

    def invalidate(self, store_name):
        self.invalidated.append(store_name)


@pytest.mark.asyncio
class TestTokenIntegration:
    """The client resolves its auth header via the token provider."""

    async def test_auth_header_uses_provider_token(self):
        """The X-Shopify-Access-Token header comes from the token provider."""
        provider = _SeqProvider("shpat_resolved")
        mock_response = _make_mock_response(200, {"data": {}})
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient(token_provider=provider)
            await client.execute_query(CREDS_CONFIG, "{ shop { name } }")

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["X-Shopify-Access-Token"] == "shpat_resolved"

    async def test_401_credentials_store_refreshes_and_retries(self):
        """A 401 on a client_credentials store invalidates the token and retries once."""
        provider = _SeqProvider("tok-old", "tok-new")
        mock_client = _make_mock_client(
            post_side_effect=[
                _make_mock_response(401),
                _make_mock_response(200, {"data": {"shop": {"name": "OK"}}}),
            ]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient(token_provider=provider)
            client.retry_delays = [0, 0, 0]
            result = await client.execute_query(CREDS_CONFIG, "{ shop { name } }")

        assert result == {"data": {"shop": {"name": "OK"}}}
        assert provider.invalidated == ["creds"]
        assert mock_client.post.await_count == 2
        second_headers = mock_client.post.call_args_list[1].kwargs["headers"]
        assert second_headers["X-Shopify-Access-Token"] == "tok-new"

    async def test_401_credentials_store_raises_after_one_refresh(self):
        """If the refreshed token is still 401, the client gives up and raises."""
        provider = _SeqProvider("tok-old", "tok-new")
        mock_client = _make_mock_client(
            post_side_effect=[_make_mock_response(401), _make_mock_response(401)]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient(token_provider=provider)
            client.retry_delays = [0, 0, 0]
            with pytest.raises(ShopifyAuthError):
                await client.execute_query(CREDS_CONFIG, "{ shop { name } }")

        assert provider.invalidated == ["creds"]
        assert mock_client.post.await_count == 2


@pytest.mark.asyncio
class TestGraphQLClient:
    """Tests for GraphQLClient.execute_query."""

    async def test_success_200_returns_full_body(self):
        """Successful 200 response returns the full parsed body (data + extensions)."""
        mock_response = _make_mock_response(200, {"data": {"products": []}})
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            result = await client.execute_query(
                STORE_CONFIG, "query { products { edges { node { id } } } }"
            )

        assert result == {"data": {"products": []}}

    async def test_success_200_includes_extensions(self):
        """When Shopify returns extensions (e.g. cost), they are passed through."""
        body = {
            "data": {"shop": {"name": "Test"}},
            "extensions": {
                "cost": {
                    "requestedQueryCost": 5,
                    "actualQueryCost": 4,
                    "throttleStatus": {"maximumAvailable": 1000.0},
                }
            },
        }
        mock_response = _make_mock_response(200, body)
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            result = await client.execute_query(STORE_CONFIG, "{ shop { name } }")

        assert result["data"] == {"shop": {"name": "Test"}}
        assert result["extensions"]["cost"]["actualQueryCost"] == 4

    async def test_401_auth_error(self):
        """401 response raises ShopifyAuthError immediately."""
        mock_response = _make_mock_response(401)
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            with pytest.raises(ShopifyAuthError, match="Invalid access token"):
                await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        # Auth errors should not retry -- only one call made
        assert mock_client.post.await_count == 1

    async def test_404_not_found(self):
        """404 response raises ShopifyNotFoundError immediately."""
        mock_response = _make_mock_response(404)
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            with pytest.raises(ShopifyNotFoundError, match="Endpoint not found"):
                await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        # Not-found errors should not retry -- only one call made
        assert mock_client.post.await_count == 1

    async def test_429_retries_then_raises(self):
        """After max_retries 429 responses, raises ShopifyRateLimitError."""
        mock_response_429 = _make_mock_response(429)
        mock_client = _make_mock_client(
            post_side_effect=[mock_response_429, mock_response_429, mock_response_429]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            with pytest.raises(ShopifyRateLimitError, match="Rate limit exceeded"):
                await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        assert mock_client.post.await_count == 3

    async def test_5xx_retries_then_succeeds(self):
        """First call returns 500, second returns 200. Verify success."""
        mock_response_500 = _make_mock_response(500)
        mock_response_200 = _make_mock_response(
            200, {"data": {"shop": {"name": "Test Shop"}}}
        )
        mock_client = _make_mock_client(
            post_side_effect=[mock_response_500, mock_response_200]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            result = await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        assert result == {"data": {"shop": {"name": "Test Shop"}}}
        assert mock_client.post.await_count == 2

    async def test_graphql_errors_in_response_pass_through(self):
        """Response with 'errors' key is returned in the body, not raised.

        execute_graphql tool callers need to see GraphQL errors as data so the
        model can read and react. Only transport-level failures raise.
        """
        body = {"errors": [{"message": "Something failed"}], "data": None}
        mock_response = _make_mock_response(200, body)
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            result = await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        assert result == body

    async def test_5xx_retries_exhausted(self):
        """All 3 retry attempts return 500 — raises ShopifyAPIError."""
        mock_response_500 = _make_mock_response(500)
        mock_client = _make_mock_client(
            post_side_effect=[mock_response_500, mock_response_500, mock_response_500]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            with pytest.raises(ShopifyAPIError, match="Server error 500 after 3 retries"):
                await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        assert mock_client.post.await_count == 3

    async def test_429_retry_then_success(self):
        """First call returns 429, second call returns 200 with valid data."""
        mock_response_429 = _make_mock_response(429)
        mock_response_200 = _make_mock_response(
            200, {"data": {"shop": {"name": "Test Shop"}}}
        )
        mock_client = _make_mock_client(
            post_side_effect=[mock_response_429, mock_response_200]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            result = await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        assert result == {"data": {"shop": {"name": "Test Shop"}}}
        assert mock_client.post.await_count == 2

    async def test_network_error_retry_then_success(self):
        """First call raises httpx.ConnectError, second call succeeds."""
        import httpx as httpx_module

        mock_response_200 = _make_mock_response(
            200, {"data": {"shop": {"name": "Test Shop"}}}
        )
        mock_client = _make_mock_client(
            post_side_effect=[
                httpx_module.ConnectError("Connection refused"),
                mock_response_200,
            ]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            result = await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        assert result == {"data": {"shop": {"name": "Test Shop"}}}
        assert mock_client.post.await_count == 2

    async def test_network_error_retries_exhausted(self):
        """All retry attempts raise network errors — raises ShopifyAPIError."""
        import httpx as httpx_module

        mock_client = _make_mock_client(
            post_side_effect=[
                httpx_module.ConnectError("Connection refused"),
                httpx_module.ConnectError("Connection refused"),
                httpx_module.ConnectError("Connection refused"),
            ]
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            with pytest.raises(ShopifyAPIError, match="Network error after 3 retries"):
                await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        assert mock_client.post.await_count == 3

    async def test_json_parse_failure(self):
        """Response is 200 but body is not valid JSON — raises ShopifyAPIError."""
        mock_response = _make_mock_response(200)
        mock_response.json.side_effect = ValueError("Expecting value: line 1 column 1")
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()

            with pytest.raises(ShopifyAPIError, match="Failed to parse JSON response"):
                await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        # JSON parse errors are not retried — only one call made
        assert mock_client.post.await_count == 1

    async def test_non_standard_error_status(self):
        """A 403 Forbidden response raises ShopifyAPIError with HTTP status."""
        mock_response = _make_mock_response(403, text="Forbidden")
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            client.retry_delays = [0, 0, 0]

            with pytest.raises(ShopifyAPIError, match="HTTP 403"):
                await client.execute_query(STORE_CONFIG, "query { shop { name } }")

        # Non-standard errors are not retried — only one call made
        assert mock_client.post.await_count == 1

    async def test_uses_api_version_env_var(self, monkeypatch):
        """SHOPIFY_API_VERSION env var controls the URL path version segment."""
        monkeypatch.setenv("SHOPIFY_API_VERSION", "2025-01")
        mock_response = _make_mock_response(200, {"data": {}})
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            await client.execute_query(STORE_CONFIG, "{ shop { name } }")

        called_url = mock_client.post.call_args[0][0]
        assert "/admin/api/2025-01/graphql.json" in called_url

    async def test_default_api_version_is_2024_10(self, monkeypatch):
        """Without SHOPIFY_API_VERSION set, the default is 2024-10."""
        monkeypatch.delenv("SHOPIFY_API_VERSION", raising=False)
        mock_response = _make_mock_response(200, {"data": {}})
        mock_client = _make_mock_client(post_return=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = GraphQLClient()
            await client.execute_query(STORE_CONFIG, "{ shop { name } }")

        called_url = mock_client.post.call_args[0][0]
        assert "/admin/api/2024-10/graphql.json" in called_url
