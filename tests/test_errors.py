"""Tests for the Shopify error hierarchy."""

import pytest

from shopify_meta.utils.errors import (
    ShopifyAPIError,
    ShopifyAuthError,
    ShopifyError,
    ShopifyNotFoundError,
    ShopifyRateLimitError,
)


def test_shopify_error_message_without_store_name():
    err = ShopifyError("Something failed")
    assert str(err) == "Something failed"
    assert err.store_name is None


def test_shopify_error_prepends_store_name():
    err = ShopifyError("Something failed", store_name="my-store")
    assert str(err) == "[my-store] Something failed"
    assert err.store_name == "my-store"


def test_all_subclasses_inherit_store_name_behavior():
    for cls in (
        ShopifyAuthError,
        ShopifyNotFoundError,
        ShopifyRateLimitError,
        ShopifyAPIError,
    ):
        err = cls("boom", store_name="s1")
        assert isinstance(err, ShopifyError)
        assert err.store_name == "s1"
        assert "[s1]" in str(err)


def test_subclasses_are_distinct():
    assert ShopifyAuthError is not ShopifyAPIError
    assert not isinstance(ShopifyAuthError("x"), ShopifyNotFoundError)
