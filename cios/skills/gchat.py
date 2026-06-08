"""Google Chat skill — search, list, send messages via Google MCP.

Requires: user logged into Intelligence with workspace=true.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def list_spaces(mcp_client, max_results: int = 20) -> dict[str, Any]:
    """List Google Chat spaces (rooms/DMs).

    Returns:
        {"spaces": [{"name", "displayName", "type"}], "count": int}
    """
    try:
        result = mcp_client.call(
            "chat",
            "list_spaces",
            {
                "maxResults": max_results,
            },
        )
        return result
    except Exception as e:
        logger.error("Chat list spaces failed: %s", e)
        return {"error": str(e), "spaces": [], "count": 0}


def search_messages(mcp_client, query: str, max_results: int = 10) -> dict[str, Any]:
    """Search messages across Google Chat spaces.

    Args:
        query: Search query
        max_results: Maximum results

    Returns:
        {"messages": [{"text", "sender", "space", "createTime"}], "count": int}
    """
    try:
        result = mcp_client.call(
            "chat",
            "search_messages",
            {
                "query": query,
                "maxResults": max_results,
            },
        )
        return result
    except Exception as e:
        logger.error("Chat search failed: %s", e)
        return {"error": str(e), "messages": [], "count": 0}


def send_message(mcp_client, space: str, text: str) -> dict[str, Any]:
    """Send a message to a Google Chat space.

    Args:
        space: Space name/ID
        text: Message text

    Returns:
        {"message_id": str, "status": "sent"}
    """
    try:
        result = mcp_client.call(
            "chat",
            "create_message",
            {
                "space": space,
                "text": text,
            },
        )
        return result
    except Exception as e:
        logger.error("Chat send failed: %s", e)
        return {"error": str(e)}
