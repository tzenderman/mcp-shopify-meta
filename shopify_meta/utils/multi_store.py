"""Multi-store configuration management."""

import json
import os
from typing import TypedDict

from .errors import ShopifyError


class StoreConfig(TypedDict):
    """Type definition for store configuration."""

    store_name: str
    shopify_url: str
    token: str


class MultiStoreManager:
    """Manages multiple Shopify store configurations."""

    def __init__(self):
        self._stores: list[StoreConfig] = []
        self._load_stores()

    def _load_stores(self) -> None:
        """Load stores from SHOPIFY_STORES environment variable."""
        stores_json = os.getenv("SHOPIFY_STORES")
        if not stores_json:
            raise ShopifyError(
                "SHOPIFY_STORES environment variable not set. "
                "Set it to a JSON array of store configurations."
            )

        try:
            stores = json.loads(stores_json)
        except json.JSONDecodeError as e:
            raise ShopifyError(f"Invalid JSON in SHOPIFY_STORES: {e}")

        if not isinstance(stores, list):
            raise ShopifyError("SHOPIFY_STORES must be a JSON array")

        if len(stores) == 0:
            raise ShopifyError("SHOPIFY_STORES array is empty")

        for idx, store in enumerate(stores):
            self._validate_store(store, idx)

        self._stores = stores

        names = [s["store_name"] for s in self._stores]
        if len(names) != len(set(names)):
            raise ShopifyError("Duplicate store_name values in SHOPIFY_STORES")

    def _validate_store(self, store: dict, idx: int) -> None:
        """Validate a single store configuration."""
        required_keys = {"store_name", "shopify_url", "token"}
        if not isinstance(store, dict):
            raise ShopifyError(f"Store at index {idx} is not an object")

        missing = required_keys - set(store.keys())
        if missing:
            raise ShopifyError(
                f"Store at index {idx} missing keys: {', '.join(sorted(missing))}"
            )

        if not store["shopify_url"].startswith("https://"):
            raise ShopifyError(
                f"Store '{store['store_name']}' has invalid shopify_url: "
                "must start with https://"
            )

    def get_store_config(self, store_name: str | None) -> StoreConfig:
        """Get configuration for a specific store.

        Args:
            store_name: Name of the store. Required.

        Returns:
            Store configuration dict.

        Raises:
            ShopifyError: If store_name is not provided or not found.
        """
        if not store_name:
            available = [s["store_name"] for s in self._stores]
            raise ShopifyError(
                f"store_name is required. Available stores: {', '.join(available)}"
            )

        for store in self._stores:
            if store["store_name"] == store_name:
                return store

        available = [s["store_name"] for s in self._stores]
        raise ShopifyError(
            f"Store '{store_name}' not found. Available stores: {', '.join(available)}"
        )

    def list_stores(self) -> list[str]:
        """Return list of all configured store names."""
        return [s["store_name"] for s in self._stores]


_manager: MultiStoreManager | None = None


def get_store_manager() -> MultiStoreManager:
    """Get or create the global MultiStoreManager instance."""
    global _manager
    if _manager is None:
        _manager = MultiStoreManager()
    return _manager
