"""Atrium (and any installer) launches local MCP servers through a console
script the package installs into its venv's bin/ — never `python -m`. The
installed metadata must expose one that resolves to the stdio entry point."""

from importlib.metadata import entry_points

from shopify_meta import server_stdio


def test_console_script_launches_stdio_server():
    (ep,) = entry_points(group="console_scripts", name="mcp-shopify-meta")
    assert ep.load() is server_stdio.main
