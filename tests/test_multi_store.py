"""Tests for multi-store configuration management."""

import json

import pytest

import shopify_meta.utils.multi_store as multi_store_module
from shopify_meta.utils.errors import ShopifyError
from shopify_meta.utils.multi_store import MultiStoreManager


def _make_store(
    name="test-store",
    url="https://test-store.myshopify.com",
    token="shpat_test123",
):
    """Helper to build a valid store config dict."""
    return {"store_name": name, "shopify_url": url, "token": token}


@pytest.fixture(autouse=True)
def _reset_global_manager():
    """Reset the global singleton before every test."""
    multi_store_module._manager = None
    yield
    multi_store_module._manager = None


class TestLoadStores:
    """Tests for MultiStoreManager._load_stores (called in __init__)."""

    def test_load_stores_success(self, monkeypatch):
        """Valid JSON array with one store loads successfully."""
        stores = [_make_store()]
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps(stores))

        manager = MultiStoreManager()
        assert manager._stores == stores

    def test_load_stores_missing_env(self, monkeypatch):
        """No SHOPIFY_STORES env var raises ShopifyError."""
        monkeypatch.delenv("SHOPIFY_STORES", raising=False)

        with pytest.raises(ShopifyError, match="SHOPIFY_STORES environment variable not set"):
            MultiStoreManager()

    def test_load_stores_invalid_json(self, monkeypatch):
        """Malformed JSON raises ShopifyError."""
        monkeypatch.setenv("SHOPIFY_STORES", "{not valid json!!")

        with pytest.raises(ShopifyError, match="Invalid JSON in SHOPIFY_STORES"):
            MultiStoreManager()

    def test_load_stores_not_array(self, monkeypatch):
        """JSON that is a dict (not an array) raises ShopifyError."""
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps({"store_name": "x"}))

        with pytest.raises(ShopifyError, match="SHOPIFY_STORES must be a JSON array"):
            MultiStoreManager()

    def test_load_stores_empty(self, monkeypatch):
        """Empty array raises ShopifyError."""
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps([]))

        with pytest.raises(ShopifyError, match="SHOPIFY_STORES array is empty"):
            MultiStoreManager()

    def test_load_stores_missing_keys(self, monkeypatch):
        """Store missing required keys raises ShopifyError."""
        stores = [{"store_name": "x"}]  # missing shopify_url and token
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps(stores))

        with pytest.raises(ShopifyError, match="Store at index 0 missing keys"):
            MultiStoreManager()

    def test_load_stores_invalid_url(self, monkeypatch):
        """shopify_url that doesn't start with https:// raises ShopifyError."""
        stores = [_make_store(url="http://bad-url.myshopify.com")]
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps(stores))

        with pytest.raises(ShopifyError, match="invalid shopify_url.*must start with https://"):
            MultiStoreManager()


class TestClientCredentialsStores:
    """Stores may authenticate via client_id + client_secret instead of a static token."""

    def test_load_store_with_client_credentials(self, monkeypatch):
        """A store with client_id + client_secret and no token loads successfully."""
        store = {
            "store_name": "creds-store",
            "shopify_url": "https://creds-store.myshopify.com",
            "client_id": "abc123",
            "client_secret": "shh-secret",
        }
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps([store]))

        manager = MultiStoreManager()

        assert manager.get_store_config("creds-store")["client_id"] == "abc123"

    def test_load_store_with_neither_token_nor_credentials(self, monkeypatch):
        """A store with neither token nor client credentials raises ShopifyError."""
        store = {
            "store_name": "broken",
            "shopify_url": "https://broken.myshopify.com",
        }
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps([store]))

        with pytest.raises(ShopifyError, match="must define either 'token' or both 'client_id' and 'client_secret'"):
            MultiStoreManager()

    def test_load_store_with_client_id_but_no_secret(self, monkeypatch):
        """A store with client_id but no client_secret raises ShopifyError."""
        store = {
            "store_name": "half",
            "shopify_url": "https://half.myshopify.com",
            "client_id": "abc123",
        }
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps([store]))

        with pytest.raises(ShopifyError, match="must define either 'token' or both 'client_id' and 'client_secret'"):
            MultiStoreManager()


class TestGetStoreConfig:
    """Tests for MultiStoreManager.get_store_config."""

    def test_get_store_config_requires_store_name(self, monkeypatch):
        """store_name is required — None or empty string raises ShopifyError."""
        store_a = _make_store(name="store-a")
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps([store_a]))

        manager = MultiStoreManager()

        with pytest.raises(ShopifyError, match="store_name is required"):
            manager.get_store_config(None)

        with pytest.raises(ShopifyError, match="store_name is required"):
            manager.get_store_config("")

    def test_get_store_config_by_name(self, monkeypatch):
        """Specific store_name returns the matching store."""
        store_a = _make_store(name="store-a")
        store_b = _make_store(name="store-b", url="https://store-b.myshopify.com")
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps([store_a, store_b]))

        manager = MultiStoreManager()
        result = manager.get_store_config("store-b")

        assert result["store_name"] == "store-b"
        assert result["shopify_url"] == "https://store-b.myshopify.com"

    def test_get_store_config_not_found(self, monkeypatch):
        """Unknown store_name raises ShopifyError."""
        stores = [_make_store(name="only-store")]
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps(stores))

        manager = MultiStoreManager()

        with pytest.raises(ShopifyError, match="Store 'nonexistent' not found"):
            manager.get_store_config("nonexistent")


class TestListStores:
    def test_list_stores_returns_names(self, monkeypatch):
        stores = [_make_store(name="a"), _make_store(name="b", url="https://b.myshopify.com")]
        monkeypatch.setenv("SHOPIFY_STORES", json.dumps(stores))

        manager = MultiStoreManager()
        assert manager.list_stores() == ["a", "b"]
