"""Google Calendar skill — list, create, update events via Google MCP.

Requires: user logged into Intelligence with workspace=true.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def list_events(mcp_client, days: int = 7, max_results: int = 20) -> dict[str, Any]:
    """List upcoming calendar events.

    Args:
        mcp_client: GoogleMCPClient instance
        days: Number of days ahead to look
        max_results: Maximum events to return

    Returns:
        {"events": [{"id", "summary", "start", "end", "location"}], "count": int}
    """
    try:
        result = mcp_client.call(
            "calendar",
            "list_events",
            {
                "daysAhead": days,
                "maxResults": max_results,
            },
        )
        return result
    except Exception as e:
        logger.error("Calendar list failed: %s", e)
        return {"error": str(e), "events": [], "count": 0}


def create_event(
    mcp_client,
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
) -> dict[str, Any]:
    """Create a new calendar event.

    Args:
        summary: Event title
        start: Start time (ISO 8601)
        end: End time (ISO 8601)
        description: Event description
        location: Event location

    Returns:
        {"event_id": str, "htmlLink": str, "status": "created"}
    """
    try:
        result = mcp_client.call(
            "calendar",
            "create_event",
            {
                "summary": summary,
                "start": start,
                "end": end,
                "description": description,
                "location": location,
            },
        )
        return result
    except Exception as e:
        logger.error("Calendar create failed: %s", e)
        return {"error": str(e)}


def update_event(mcp_client, event_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update an existing calendar event.

    Args:
        event_id: Event ID to update
        updates: Fields to update (summary, start, end, description, location)

    Returns:
        {"event_id": str, "status": "updated"}
    """
    try:
        result = mcp_client.call(
            "calendar",
            "update_event",
            {
                "eventId": event_id,
                **updates,
            },
        )
        return result
    except Exception as e:
        logger.error("Calendar update failed: %s", e)
        return {"error": str(e)}
