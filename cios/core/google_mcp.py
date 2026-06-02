"""Google MCP Client — OS-side client for Google Workspace MCP servers.

Gets a fresh access_token from Maestro API, then calls Google MCP servers directly.
This avoids routing every Google operation through the chat pipeline.

Flow:
    1. OS calls GET /v1/auth/google/token → gets fresh access_token
    2. OS calls Google MCP server directly with that token
    3. Results are returned to the skill/handler

Requires: user logged into Intelligence (has refresh_token stored in Maestro).
"""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Google MCP server endpoints
MCP_ENDPOINTS = {
    "gmail": "https://gmailmcp.googleapis.com/mcp/v1",
    "drive": "https://drivemcp.googleapis.com/mcp/v1",
    "calendar": "https://calendarmcp.googleapis.com/mcp/v1",
    "chat": "https://chatmcp.googleapis.com/mcp/v1",
    "people": "https://people.googleapis.com/mcp/v1",
}

MCP_TIMEOUT = 15


class GoogleMCPError(Exception):
    """Raised when a Google MCP call fails."""

    def __init__(self, service: str, tool: str, message: str):
        self.service = service
        self.tool = tool
        super().__init__(f"[{service}/{tool}] {message}")


class GoogleMCPClient:
    """OS-side client for Google Workspace MCP servers.

    Gets token from Maestro, calls Google MCP directly.
    """

    def __init__(self, api_url: str, jwt_token: str):
        """Initialize with Maestro API URL and user's JWT.

        Args:
            api_url: Maestro API base URL (e.g. https://api.cios-ai.com)
            jwt_token: User's JWT token for Maestro auth
        """
        self.api_url = api_url.rstrip("/")
        self.jwt_token = jwt_token
        self._access_token: str | None = None

    def call(
        self,
        service: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a tool on a Google MCP server.

        Args:
            service: MCP server name (gmail, drive, calendar, chat, people)
            tool: Tool name (e.g. "search_emails", "list_files")
            arguments: Tool arguments

        Returns:
            Tool result as dict

        Raises:
            GoogleMCPError: If the call fails
        """
        if service not in MCP_ENDPOINTS:
            raise GoogleMCPError(service, tool, f"Unknown service: {service}")

        # Get fresh access token from Maestro
        access_token = self._get_access_token()

        # Build MCP request (JSON-RPC 2.0)
        endpoint = MCP_ENDPOINTS[service]
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": arguments or {},
            },
        }

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=MCP_TIMEOUT,
            )

            if response.status_code == 401:
                # Token expired — refresh and retry
                self._access_token = None
                access_token = self._get_access_token()
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=MCP_TIMEOUT,
                )

            if response.status_code != 200:
                raise GoogleMCPError(
                    service, tool,
                    f"HTTP {response.status_code}: {response.text[:200]}",
                )

            result = response.json()

            if "error" in result:
                error = result["error"]
                raise GoogleMCPError(service, tool, f"MCP error: {error.get('message', str(error))}")

            return result.get("result", {})

        except requests.RequestException as e:
            raise GoogleMCPError(service, tool, f"Network error: {str(e)}") from e

    def has_workspace_access(self) -> bool:
        """Check if user has Google Workspace connected (via Maestro /me)."""
        try:
            response = requests.get(
                f"{self.api_url}/v1/auth/me",
                headers={"Authorization": f"Bearer {self.jwt_token}"},
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("user", {}).get("has_workspace", False)
        except Exception:
            pass
        return False

    def _get_access_token(self) -> str:
        """Get fresh Google access_token from Maestro."""
        if self._access_token:
            return self._access_token

        try:
            response = requests.get(
                f"{self.api_url}/v1/auth/google/token",
                headers={"Authorization": f"Bearer {self.jwt_token}"},
                timeout=8,
            )

            if response.status_code == 403:
                raise GoogleMCPError(
                    "auth", "token",
                    "Google Workspace not connected. Login to Intelligence with workspace=true.",
                )

            if response.status_code != 200:
                raise GoogleMCPError(
                    "auth", "token",
                    f"Failed to get token: HTTP {response.status_code}",
                )

            data = response.json()
            self._access_token = data["access_token"]
            return self._access_token

        except requests.RequestException as e:
            raise GoogleMCPError("auth", "token", f"Network error: {str(e)}") from e
