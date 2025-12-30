"""
Tests for bunny_client.py - HTTP client with authentication and retry logic.
"""

import time
from unittest.mock import Mock, patch

import pytest

from bunny_client import (
    BunnyClient,
    BunnyAPIError,
    BunnyAuthError,
    BunnyForbiddenError,
    BunnyNotFoundError,
    BunnyRateLimitError,
    BunnyValidationError,
)


class TestBunnyClientInit:
    """Test BunnyClient initialization."""

    def test_init_sets_api_key(self):
        client = BunnyClient("my-api-key")
        assert client.api_key == "my-api-key"

    def test_init_sets_default_retries(self):
        client = BunnyClient("key")
        assert client.max_retries == 3
        assert client.retry_delay == 1.0

    def test_init_sets_custom_retries(self):
        client = BunnyClient("key", max_retries=5, retry_delay=2.0)
        assert client.max_retries == 5
        assert client.retry_delay == 2.0

    def test_init_sets_headers(self):
        client = BunnyClient("test-key")
        assert client.session.headers["AccessKey"] == "test-key"
        assert client.session.headers["Content-Type"] == "application/json"
        assert client.session.headers["Accept"] == "application/json"


class TestHandleResponse:
    """Test response handling and exception raising."""

    def test_200_returns_json(self, mock_client, mock_response):
        response = mock_response(200, {"data": "test"})
        result = mock_client._handle_response(response)
        assert result == {"data": "test"}

    def test_201_returns_json(self, mock_client, mock_response):
        response = mock_response(201, {"id": 123})
        result = mock_client._handle_response(response)
        assert result == {"id": 123}

    def test_204_returns_none(self, mock_client, mock_response):
        response = mock_response(204, None, text="")
        response.json.side_effect = ValueError("No JSON")
        result = mock_client._handle_response(response)
        assert result is None

    def test_400_raises_validation_error(self, mock_client, mock_response):
        response = mock_response(400, {"error": "invalid field"})
        with pytest.raises(BunnyValidationError) as exc:
            mock_client._handle_response(response)
        assert exc.value.status_code == 400

    def test_401_raises_auth_error(self, mock_client, mock_response):
        response = mock_response(401, None)
        with pytest.raises(BunnyAuthError) as exc:
            mock_client._handle_response(response)
        assert exc.value.status_code == 401
        assert "Authentication failed" in str(exc.value)

    def test_403_raises_forbidden_error(self, mock_client, mock_response):
        response = mock_response(403, {"message": "forbidden"})
        with pytest.raises(BunnyForbiddenError) as exc:
            mock_client._handle_response(response)
        assert exc.value.status_code == 403

    def test_404_raises_not_found_error(self, mock_client, mock_response):
        response = mock_response(404, {"message": "not found"})
        with pytest.raises(BunnyNotFoundError) as exc:
            mock_client._handle_response(response)
        assert exc.value.status_code == 404

    def test_429_raises_rate_limit_error(self, mock_client, mock_response):
        response = mock_response(429, None)
        with pytest.raises(BunnyRateLimitError) as exc:
            mock_client._handle_response(response)
        assert exc.value.status_code == 429

    def test_500_raises_generic_api_error(self, mock_client, mock_response):
        response = mock_response(500, {"error": "server error"})
        with pytest.raises(BunnyAPIError) as exc:
            mock_client._handle_response(response)
        assert exc.value.status_code == 500

    def test_handles_invalid_json(self, mock_client, mock_response):
        response = mock_response(200, None, text="not json")
        response.json.side_effect = ValueError("Invalid JSON")
        result = mock_client._handle_response(response)
        assert result is None


class TestRequest:
    """Test the _request method with retry logic."""

    def test_successful_request(self, mock_client, mock_response):
        response = mock_response(200, {"result": "ok"})
        mock_client.session.request.return_value = response

        result = mock_client._request("GET", "/test")

        mock_client.session.request.assert_called_once_with(
            method="GET",
            url="https://api.bunny.net/test",
            params=None,
            json=None,
        )
        assert result == {"result": "ok"}

    def test_passes_params(self, mock_client, mock_response):
        response = mock_response(200, {"result": "ok"})
        mock_client.session.request.return_value = response

        mock_client._request("GET", "/test", params={"key": "value"})

        mock_client.session.request.assert_called_with(
            method="GET",
            url="https://api.bunny.net/test",
            params={"key": "value"},
            json=None,
        )

    def test_passes_json_data(self, mock_client, mock_response):
        response = mock_response(201, {"id": 1})
        mock_client.session.request.return_value = response

        mock_client._request("POST", "/test", json_data={"name": "test"})

        mock_client.session.request.assert_called_with(
            method="POST",
            url="https://api.bunny.net/test",
            params=None,
            json={"name": "test"},
        )

    def test_retries_on_rate_limit(self, mock_client, mock_response):
        mock_client.max_retries = 2
        mock_client.retry_delay = 0.01  # Speed up test

        rate_limit_response = mock_response(429, None)
        success_response = mock_response(200, {"result": "ok"})

        mock_client.session.request.side_effect = [
            rate_limit_response,
            success_response,
        ]

        with patch("time.sleep"):
            result = mock_client._request("GET", "/test")

        assert result == {"result": "ok"}
        assert mock_client.session.request.call_count == 2

    def test_raises_after_max_retries(self, mock_client, mock_response):
        mock_client.max_retries = 2
        mock_client.retry_delay = 0.01

        rate_limit_response = mock_response(429, None)
        mock_client.session.request.return_value = rate_limit_response

        with patch("time.sleep"):
            with pytest.raises(BunnyRateLimitError):
                mock_client._request("GET", "/test")

        # Initial attempt + 2 retries = 3 calls
        assert mock_client.session.request.call_count == 3

    def test_exponential_backoff(self, mock_client, mock_response):
        mock_client.max_retries = 3
        mock_client.retry_delay = 1.0

        rate_limit_response = mock_response(429, None)
        success_response = mock_response(200, {"ok": True})

        mock_client.session.request.side_effect = [
            rate_limit_response,
            rate_limit_response,
            success_response,
        ]

        sleep_calls = []
        with patch("time.sleep", side_effect=lambda x: sleep_calls.append(x)):
            mock_client._request("GET", "/test")

        # First retry: 1.0 * 2^0 = 1.0
        # Second retry: 1.0 * 2^1 = 2.0
        assert sleep_calls == [1.0, 2.0]


class TestHTTPMethods:
    """Test convenience HTTP method wrappers."""

    def test_get_method(self, mock_client, mock_response):
        response = mock_response(200, {"items": []})
        mock_client.session.request.return_value = response

        result = mock_client.get("/dnszone", params={"page": 1})

        mock_client.session.request.assert_called_with(
            method="GET",
            url="https://api.bunny.net/dnszone",
            params={"page": 1},
            json=None,
        )
        assert result == {"items": []}

    def test_post_method(self, mock_client, mock_response):
        response = mock_response(201, {"Id": 123})
        mock_client.session.request.return_value = response

        result = mock_client.post("/dnszone", data={"Domain": "test.com"})

        mock_client.session.request.assert_called_with(
            method="POST",
            url="https://api.bunny.net/dnszone",
            params=None,
            json={"Domain": "test.com"},
        )
        assert result == {"Id": 123}

    def test_put_method(self, mock_client, mock_response):
        response = mock_response(200, {"Id": 1})
        mock_client.session.request.return_value = response

        result = mock_client.put("/dnszone/1/records", data={"Type": 0})

        mock_client.session.request.assert_called_with(
            method="PUT",
            url="https://api.bunny.net/dnszone/1/records",
            params=None,
            json={"Type": 0},
        )
        assert result == {"Id": 1}

    def test_delete_method(self, mock_client, mock_response):
        response = mock_response(204, None, text="")
        response.json.side_effect = ValueError()
        mock_client.session.request.return_value = response

        result = mock_client.delete("/dnszone/1", params={"confirm": "true"})

        mock_client.session.request.assert_called_with(
            method="DELETE",
            url="https://api.bunny.net/dnszone/1",
            params={"confirm": "true"},
            json=None,
        )
        assert result is None


class TestExceptionAttributes:
    """Test that exceptions have correct attributes."""

    def test_api_error_attributes(self):
        error = BunnyAPIError("Test error", status_code=500, response={"msg": "fail"})
        assert str(error) == "Test error"
        assert error.status_code == 500
        assert error.response == {"msg": "fail"}

    def test_api_error_inheritance(self):
        assert issubclass(BunnyAuthError, BunnyAPIError)
        assert issubclass(BunnyForbiddenError, BunnyAPIError)
        assert issubclass(BunnyNotFoundError, BunnyAPIError)
        assert issubclass(BunnyRateLimitError, BunnyAPIError)
        assert issubclass(BunnyValidationError, BunnyAPIError)
