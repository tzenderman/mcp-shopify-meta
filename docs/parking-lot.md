# Parking lot

Unresolved items, not yet worked through.

- **Bump the Shopify API version** off `2024-10` (no longer supported) to the latest stable version: the env default, the vendored schema `shopify_meta/schema/admin_<version>.json`, and `render.yaml`. Find the current stable version with `{ publicApiVersions { handle supported } }` through the live connector. Don't go by the CLI writing `2027-01` into the app config; that's just a default and not proof.
- **Let anyone connect any Shopify store over OAuth.** Not decided yet: a public app with Shopify's install flow (needs App Store review) vs. merchants pasting their own credentials. Both need per-user token storage and keeping each user to their own stores.
