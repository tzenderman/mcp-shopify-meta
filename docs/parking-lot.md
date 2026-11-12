# Parking lot

Unresolved items, not yet worked through.

- **Render ignores `uv.lock`.** `buildCommand: pip install -e .` installs whatever is newest within the pyproject bounds at build time, so the audited lock isn't what runs in production. Consider `uv sync --frozen` on Render. Same for mcp-cin7-meta.
- **Let anyone connect any Shopify store over OAuth.** Not decided yet: a public app with Shopify's install flow (needs App Store review) vs. merchants pasting their own credentials. Both need per-user token storage and keeping each user to their own stores.
