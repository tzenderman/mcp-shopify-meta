"""Resolves a store's Admin API access token.

Two authentication styles are supported per store:

- **Static token** — the store config carries a permanent ``token`` (legacy
  in-store custom apps). It is returned verbatim, no network call.
- **Client credentials** — the store config carries ``client_id`` +
  ``client_secret`` (new Dev Dashboard apps). These are exchanged for a
  short-lived ``client_credentials`` token at the store's OAuth endpoint, then
  cached in memory with its expiry. The token is re-fetched once it expires or
  when explicitly invalidated (e.g. after a 401).
"""

import time
from typing import Callable

import httpx

from .errors import ShopifyAuthError
from .multi_store import StoreConfig

# Refetch this many seconds before the token's stated expiry, to avoid using a
# token that lapses mid-request.
REFRESH_MARGIN_SECONDS = 60.0


class _CachedToken:
    __slots__ = ("access_token", "expires_at")

    def __init__(self, access_token: str, expires_at: float):
        self.access_token = access_token
        self.expires_at = expires_at


class TokenProvider:
    """Resolves and caches Admin API access tokens per store."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        refresh_margin: float = REFRESH_MARGIN_SECONDS,
    ):
        self._clock = clock
        self._refresh_margin = refresh_margin
        self._cache: dict[str, _CachedToken] = {}

    def invalidate(self, store_name: str) -> None:
        """Drop any cached token for ``store_name`` so the next call re-exchanges."""
        self._cache.pop(store_name, None)

    async def get_token(self, store_config: StoreConfig) -> str:
        """Return a valid Admin API access token for the store.

        Static-``token`` stores return that token directly. Credential stores
        return a cached token if still valid, otherwise exchange for a fresh one.
        """
        static = store_config.get("token")
        if static:
            return static

        store_name = store_config["store_name"]
        cached = self._cache.get(store_name)
        if cached is not None and self._clock() < cached.expires_at - self._refresh_margin:
            return cached.access_token

        return await self._exchange(store_config)

    async def _exchange(self, store_config: StoreConfig) -> str:
        url = f"{store_config['shopify_url']}/admin/oauth/access_token"
        data = {
            "grant_type": "client_credentials",
            "client_id": store_config["client_id"],
            "client_secret": store_config["client_secret"],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data)

        if response.status_code != 200:
            raise ShopifyAuthError(
                "Failed to obtain client_credentials token "
                f"(HTTP {response.status_code}): {response.text}",
                store_name=store_config["store_name"],
            )

        try:
            body = response.json()
        except Exception as e:
            raise ShopifyAuthError(
                f"Failed to parse client_credentials token response: {e}",
                store_name=store_config["store_name"],
            )

        access_token = body.get("access_token")
        if not access_token:
            raise ShopifyAuthError(
                "client_credentials response missing access_token",
                store_name=store_config["store_name"],
            )

        expires_in = float(body.get("expires_in", 0))
        self._cache[store_config["store_name"]] = _CachedToken(
            access_token=access_token,
            expires_at=self._clock() + expires_in,
        )
        return access_token


_provider: TokenProvider | None = None


def get_token_provider() -> TokenProvider:
    """Get or create the global TokenProvider instance."""
    global _provider
    if _provider is None:
        _provider = TokenProvider()
    return _provider
