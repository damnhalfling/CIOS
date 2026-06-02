"""Google Drive skill — search, read, download, create files via Google MCP.

Requires: user logged into Intelligence with workspace=true.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def search_files(mcp_client, query: str, max_results: int = 10) -> dict[str, Any]:
    """Search files in Google Drive.

    Args:
        mcp_client: GoogleMCPClient instance
        query: Search query (file name, content, type)
        max_results: Maximum results

    Returns:
        {"files": [{"id", "name", "mimeType", "modifiedTime"}], "count": int}
    """
    try:
        result = mcp_client.call(
            "drive",
            "search_files",
            {
                "query": query,
                "maxResults": max_results,
            },
        )
        return result
    except Exception as e:
        logger.error("Drive search failed: %s", e)
        return {"error": str(e), "files": [], "count": 0}


def read_file(mcp_client, file_id: str) -> dict[str, Any]:
    """Read file content from Google Drive.

    Returns:
        {"name": str, "content": str, "mimeType": str}
    """
    try:
        result = mcp_client.call(
            "drive",
            "read_file",
            {
                "fileId": file_id,
            },
        )
        return result
    except Exception as e:
        logger.error("Drive read failed: %s", e)
        return {"error": str(e)}


def create_file(
    mcp_client, name: str, content: str, mime_type: str = "text/plain"
) -> dict[str, Any]:
    """Create a new file in Google Drive.

    Returns:
        {"file_id": str, "name": str, "webViewLink": str}
    """
    try:
        result = mcp_client.call(
            "drive",
            "create_file",
            {
                "name": name,
                "content": content,
                "mimeType": mime_type,
            },
        )
        return result
    except Exception as e:
        logger.error("Drive create failed: %s", e)
        return {"error": str(e)}


def download_file(mcp_client, file_id: str, destination: str) -> dict[str, Any]:
    """Download a file from Google Drive to local path.

    Returns:
        {"path": str, "size": int, "status": "downloaded"}
    """
    try:
        result = mcp_client.call(
            "drive",
            "export_file",
            {
                "fileId": file_id,
            },
        )
        # Write content to local file
        if "content" in result:
            with open(destination, "w") as f:
                f.write(result["content"])
            return {"path": destination, "size": len(result["content"]), "status": "downloaded"}
        return result
    except Exception as e:
        logger.error("Drive download failed: %s", e)
        return {"error": str(e)}
