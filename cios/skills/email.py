"""Gmail skill — search, read, draft, label emails via Google MCP.

Requires: user logged into Intelligence with workspace=true.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def search_emails(mcp_client, query: str, max_results: int = 10) -> dict[str, Any]:
    """Search emails matching a query.

    Args:
        mcp_client: GoogleMCPClient instance
        query: Gmail search query (e.g. "from:boss@company.com", "is:unread")
        max_results: Maximum number of results

    Returns:
        {"emails": [...], "count": int}
    """
    try:
        result = mcp_client.call(
            "gmail",
            "search_emails",
            {
                "query": query,
                "maxResults": max_results,
            },
        )
        return result
    except Exception as e:
        logger.error("Gmail search failed: %s", e)
        return {"error": str(e), "emails": [], "count": 0}


def read_email(mcp_client, message_id: str) -> dict[str, Any]:
    """Read a specific email by ID.

    Returns:
        {"subject": str, "from": str, "date": str, "body": str, "labels": [...]}
    """
    try:
        result = mcp_client.call(
            "gmail",
            "read_email",
            {
                "messageId": message_id,
            },
        )
        return result
    except Exception as e:
        logger.error("Gmail read failed: %s", e)
        return {"error": str(e)}


def draft_email(mcp_client, to: str, subject: str, body: str) -> dict[str, Any]:
    """Create a draft email.

    Returns:
        {"draft_id": str, "status": "created"}
    """
    try:
        result = mcp_client.call(
            "gmail",
            "create_draft",
            {
                "to": to,
                "subject": subject,
                "body": body,
            },
        )
        return result
    except Exception as e:
        logger.error("Gmail draft failed: %s", e)
        return {"error": str(e)}


def label_email(mcp_client, message_id: str, labels: list[str]) -> dict[str, Any]:
    """Add labels to an email.

    Returns:
        {"status": "labeled", "labels": [...]}
    """
    try:
        result = mcp_client.call(
            "gmail",
            "modify_labels",
            {
                "messageId": message_id,
                "addLabels": labels,
            },
        )
        return result
    except Exception as e:
        logger.error("Gmail label failed: %s", e)
        return {"error": str(e)}
