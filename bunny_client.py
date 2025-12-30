"""
Low-level HTTP client for bunny.net API.
"""

import time
from typing import Any, Optional

import requests


class BunnyAPIError(Exception):
    """Base exception for Bunny API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class BunnyAuthError(BunnyAPIError):
    """Authentication failed (401)."""
    pass


class BunnyForbiddenError(BunnyAPIError):
    """Action forbidden (403)."""
    pass


class BunnyNotFoundError(BunnyAPIError):
    """Resource not found (404)."""
    pass


class BunnyRateLimitError(BunnyAPIError):
    """Rate limit exceeded (429)."""
    pass


class BunnyValidationError(BunnyAPIError):
    """Validation failed (400)."""
    pass


class BunnyClient:
    """HTTP client for bunny.net API with AccessKey authentication."""

    BASE_URL = "https://api.bunny.net"

    def __init__(self, api_key: str, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize the Bunny API client.

        Args:
            api_key: Your bunny.net API key (AccessKey)
            max_retries: Maximum number of retries for rate-limited requests
            retry_delay: Base delay between retries (exponential backoff)
        """
        self.api_key = api_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update({
            "AccessKey": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _handle_response(self, response: requests.Response) -> Any:
        """Handle API response and raise appropriate exceptions."""
        status_code = response.status_code

        # Try to parse JSON response
        try:
            data = response.json() if response.text else None
        except ValueError:
            data = None

        if status_code == 200 or status_code == 201:
            return data
        elif status_code == 204:
            return None
        elif status_code == 400:
            raise BunnyValidationError(
                f"Validation failed: {data or response.text}",
                status_code=status_code,
                response=data,
            )
        elif status_code == 401:
            raise BunnyAuthError(
                "Authentication failed. Check your API key.",
                status_code=status_code,
                response=data,
            )
        elif status_code == 403:
            raise BunnyForbiddenError(
                f"Action forbidden: {data or response.text}",
                status_code=status_code,
                response=data,
            )
        elif status_code == 404:
            raise BunnyNotFoundError(
                f"Resource not found: {data or response.text}",
                status_code=status_code,
                response=data,
            )
        elif status_code == 429:
            raise BunnyRateLimitError(
                "Rate limit exceeded",
                status_code=status_code,
                response=data,
            )
        else:
            raise BunnyAPIError(
                f"API error ({status_code}): {data or response.text}",
                status_code=status_code,
                response=data,
            )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> Any:
        """
        Make an API request with automatic retry on rate limit.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/dnszone")
            params: Query parameters
            json_data: JSON body for POST/PUT requests

        Returns:
            Parsed JSON response or None
        """
        url = f"{self.BASE_URL}{endpoint}"

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )
                return self._handle_response(response)
            except BunnyRateLimitError:
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise

    def get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Make a GET request."""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, data: Optional[dict] = None) -> Any:
        """Make a POST request."""
        return self._request("POST", endpoint, json_data=data)

    def put(self, endpoint: str, data: Optional[dict] = None) -> Any:
        """Make a PUT request."""
        return self._request("PUT", endpoint, json_data=data)

    def delete(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint, params=params)
