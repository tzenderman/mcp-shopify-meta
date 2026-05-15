"""Custom exceptions for Shopify API interactions."""


class ShopifyError(Exception):
    """Base exception for Shopify-related errors."""

    def __init__(self, message: str, store_name: str | None = None):
        self.store_name = store_name
        if store_name:
            message = f"[{store_name}] {message}"
        super().__init__(message)


class ShopifyAuthError(ShopifyError):
    """Raised when authentication fails or token is invalid."""

    pass


class ShopifyNotFoundError(ShopifyError):
    """Raised when a requested resource doesn't exist."""

    pass


class ShopifyRateLimitError(ShopifyError):
    """Raised when rate limits are exceeded after retries."""

    pass


class ShopifyAPIError(ShopifyError):
    """Raised for generic Shopify API errors."""

    pass
