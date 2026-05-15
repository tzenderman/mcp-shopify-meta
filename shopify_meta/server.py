"""FastMCP server setup and tool registration for mcp-shopify-meta."""

from fastmcp import FastMCP

from .resources import execute, issues, schema
from .utils.logging import setup_logging

setup_logging()


def create_mcp_server(auth=None) -> FastMCP:
    """Create and configure the FastMCP server with the four generic tools.

    Args:
        auth: Optional auth provider (e.g., `ScalekitProvider`) for OAuth.
    """
    mcp = FastMCP(
        name="Shopify Admin Meta MCP Server",
        instructions=(
            "MCP server providing schema-walking access to the Shopify Admin "
            "GraphQL API. Use `search_schema` to find types and fields by keyword, "
            "`get_type_definition` to inspect a type's SDL, and `execute_graphql` "
            "to run a composed query or mutation. Use `report_issue` to file a "
            "structured bug report when a tool can't accomplish what you need."
        ),
        auth=auth,
    )

    mcp.tool()(schema.search_schema)
    mcp.tool()(schema.get_type_definition)
    mcp.tool()(execute.execute_graphql)
    mcp.tool()(issues.report_issue)

    return mcp
