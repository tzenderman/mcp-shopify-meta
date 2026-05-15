"""GraphQL client for the Shopify Admin API with retry logic."""

import asyncio
import os
from typing import Any

import httpx

from .errors import (
    ShopifyAPIError,
    ShopifyAuthError,
    ShopifyNotFoundError,
    ShopifyRateLimitError,
)
from .multi_store import StoreConfig

DEFAULT_API_VERSION = "2024-10"


class GraphQLClient:
    """Shopify GraphQL client with automatic retry and error handling.

    Unlike the sibling `mcp-shopify-admin` client, this one returns the full
    parsed response body (data + extensions) so callers can read
    `extensions.cost` for self-throttling.
    """

    def __init__(self):
        self.max_retries = 3
        self.retry_delays = [1.0, 2.0, 4.0]

    def _build_url(self, store_config: StoreConfig) -> str:
        version = os.getenv("SHOPIFY_API_VERSION", DEFAULT_API_VERSION)
        return f"{store_config['shopify_url']}/admin/api/{version}/graphql.json"

    async def execute_query(
        self,
        store_config: StoreConfig,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query against the Shopify Admin API.

        Returns the full parsed response body (e.g. `{"data": ..., "extensions": ...}`).

        Raises:
            ShopifyAuthError: HTTP 401.
            ShopifyNotFoundError: HTTP 404.
            ShopifyRateLimitError: HTTP 429 after retries exhausted.
            ShopifyAPIError: Other API errors or GraphQL `errors`.
        """
        url = self._build_url(store_config)
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": store_config["token"],
        }

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, json=payload, headers=headers)

                    if response.status_code == 401:
                        raise ShopifyAuthError(
                            "Invalid access token. Check SHOPIFY_STORES configuration.",
                            store_name=store_config["store_name"],
                        )

                    if response.status_code == 404:
                        raise ShopifyNotFoundError(
                            f"Endpoint not found: {url}",
                            store_name=store_config["store_name"],
                        )

                    if response.status_code == 429:
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delays[attempt])
                            continue
                        raise ShopifyRateLimitError(
                            f"Rate limit exceeded after {self.max_retries} retries",
                            store_name=store_config["store_name"],
                        )

                    if response.status_code >= 500:
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delays[attempt])
                            continue
                        raise ShopifyAPIError(
                            f"Server error {response.status_code} after {self.max_retries} retries",
                            store_name=store_config["store_name"],
                        )

                    if response.status_code != 200:
                        raise ShopifyAPIError(
                            f"HTTP {response.status_code}: {response.text}",
                            store_name=store_config["store_name"],
                        )

                    try:
                        body = response.json()
                    except Exception as e:
                        raise ShopifyAPIError(
                            f"Failed to parse JSON response: {e}",
                            store_name=store_config["store_name"],
                        )

                    # GraphQL semantic errors (200 with `errors` key) are returned
                    # to the caller so the model can read and react to them.
                    # Transport-level failures (4xx/5xx) still raise above.
                    return body

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delays[attempt])
                    continue

        raise ShopifyAPIError(
            f"Network error after {self.max_retries} retries: {last_error}",
            store_name=store_config["store_name"],
        )


_client: GraphQLClient | None = None


def get_graphql_client() -> GraphQLClient:
    """Get or create the global GraphQLClient instance."""
    global _client
    if _client is None:
        _client = GraphQLClient()
    return _client
