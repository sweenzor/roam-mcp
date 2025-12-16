"""Comprehensive unit tests for roam_api.py module."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_server_roam.roam_api import (
    AuthenticationError,
    BlockNotFoundError,
    InvalidQueryError,
    PageNotFoundError,
    RateLimitError,
    RoamAPI,
    RoamAPIError,
    ordinal_suffix,
    retry_with_backoff,
)


class TestOrdinalSuffix:
    """Tests for ordinal_suffix function."""

    def test_ordinal_suffix_st(self) -> None:
        """Test 'st' suffix for 1st, 21st, 31st."""
        assert ordinal_suffix(1) == "st"
        assert ordinal_suffix(21) == "st"
        assert ordinal_suffix(31) == "st"

    def test_ordinal_suffix_nd(self) -> None:
        """Test 'nd' suffix for 2nd, 22nd."""
        assert ordinal_suffix(2) == "nd"
        assert ordinal_suffix(22) == "nd"

    def test_ordinal_suffix_rd(self) -> None:
        """Test 'rd' suffix for 3rd, 23rd."""
        assert ordinal_suffix(3) == "rd"
        assert ordinal_suffix(23) == "rd"

    def test_ordinal_suffix_th(self) -> None:
        """Test 'th' suffix for other days."""
        assert ordinal_suffix(4) == "th"
        assert ordinal_suffix(11) == "th"
        assert ordinal_suffix(12) == "th"
        assert ordinal_suffix(13) == "th"
        assert ordinal_suffix(15) == "th"
        assert ordinal_suffix(20) == "th"
        assert ordinal_suffix(30) == "th"


class TestRetryWithBackoff:
    """Tests for retry_with_backoff decorator."""

    def test_retry_success_on_first_attempt(self) -> None:
        """Test that function succeeds on first attempt without retries."""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def successful_func() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()

        assert result == "success"
        assert call_count == 1

    @patch("mcp_server_roam.roam_api.time.sleep")
    def test_retry_success_after_failures(self, mock_sleep: MagicMock) -> None:
        """Test that function succeeds after initial failures."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            initial_backoff=1.0,
            backoff_multiplier=2.0,
            retryable_exceptions=(ConnectionError,),
        )
        def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"

        result = flaky_func()

        assert result == "success"
        assert call_count == 3
        assert mock_sleep.call_count == 2
        # Verify backoff timing
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    @patch("mcp_server_roam.roam_api.time.sleep")
    def test_retry_exhausted(self, mock_sleep: MagicMock) -> None:
        """Test that exception is raised after all retries exhausted."""
        call_count = 0

        @retry_with_backoff(
            max_retries=2,
            initial_backoff=1.0,
            retryable_exceptions=(ConnectionError,),
        )
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Connection failed")

        with pytest.raises(ConnectionError) as exc_info:
            always_fails()

        assert "Connection failed" in str(exc_info.value)
        assert call_count == 3  # Initial + 2 retries
        assert mock_sleep.call_count == 2

    @patch("mcp_server_roam.roam_api.time.sleep")
    def test_retry_max_backoff_capped(self, mock_sleep: MagicMock) -> None:
        """Test that backoff is capped at max_backoff."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            initial_backoff=4.0,
            backoff_multiplier=4.0,
            max_backoff=10.0,
            retryable_exceptions=(ConnectionError,),
        )
        def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Connection failed")

        with pytest.raises(ConnectionError):
            always_fails()

        # Backoff should be: 4.0, 10.0 (capped from 16), 10.0 (capped from 64)
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(4.0)
        # Second and third calls should be capped at 10.0
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls[1] == 10.0
        assert calls[2] == 10.0

    def test_retry_non_retryable_exception(self) -> None:
        """Test that non-retryable exceptions are raised immediately."""
        call_count = 0

        @retry_with_backoff(max_retries=3, retryable_exceptions=(ConnectionError,))
        def raises_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError) as exc_info:
            raises_value_error()

        assert "Not retryable" in str(exc_info.value)
        assert call_count == 1  # No retries for non-retryable exceptions


class TestRoamAPIInit:
    """Tests for RoamAPI initialization."""

    def test_init_with_explicit_credentials(self) -> None:
        """Test initialization with explicit credentials."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        assert api.api_token == "test-token"
        assert api.graph_name == "test-graph"

    def test_init_from_env_vars(self) -> None:
        """Test initialization from environment variables."""
        with patch.dict(
            "os.environ",
            {"ROAM_API_TOKEN": "env-token", "ROAM_GRAPH_NAME": "env-graph"},
        ):
            api = RoamAPI()
            assert api.api_token == "env-token"
            assert api.graph_name == "env-graph"

    def test_init_missing_token(self) -> None:
        """Test error when API token is missing."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(AuthenticationError) as exc_info:
                RoamAPI(graph_name="test-graph")
            assert "ROAM_API_TOKEN" in str(exc_info.value)

    def test_init_missing_graph_name(self) -> None:
        """Test error when graph name is missing."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(AuthenticationError) as exc_info:
                RoamAPI(api_token="test-token")
            assert "ROAM_GRAPH_NAME" in str(exc_info.value)


class TestSanitizeQueryInput:
    """Tests for _sanitize_query_input method."""

    def test_sanitize_normal_string(self) -> None:
        """Test sanitization of normal strings."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        assert api._sanitize_query_input("hello world") == "hello world"

    def test_sanitize_string_with_quotes(self) -> None:
        """Test sanitization escapes double quotes."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        assert api._sanitize_query_input('say "hello"') == 'say ""hello""'

    def test_sanitize_non_string_input(self) -> None:
        """Test error for non-string input."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api._sanitize_query_input(123)  # type: ignore[arg-type]
        assert "must be a string" in str(exc_info.value)

    def test_sanitize_null_bytes(self) -> None:
        """Test error for null bytes in input."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api._sanitize_query_input("hello\x00world")
        assert "null bytes" in str(exc_info.value)

    def test_sanitize_suspicious_find_pattern(self) -> None:
        """Test error for suspicious :find pattern."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api._sanitize_query_input("[:find ?e :where ...")
        assert "suspicious pattern" in str(exc_info.value)

    def test_sanitize_suspicious_where_pattern(self) -> None:
        """Test error for suspicious :where pattern."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api._sanitize_query_input("[:where [?e ...")
        assert "suspicious pattern" in str(exc_info.value)

    def test_sanitize_suspicious_variable_pattern(self) -> None:
        """Test error for suspicious variable pattern."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api._sanitize_query_input("[?b :block/string ...")
        assert "suspicious pattern" in str(exc_info.value)


class TestMaskToken:
    """Tests for _mask_token method."""

    def test_mask_long_token(self) -> None:
        """Test masking of long tokens shows first/last 4 chars."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        assert api._mask_token("abcdefghij") == "abcd...ghij"
        assert api._mask_token("123456789012") == "1234...9012"

    def test_mask_short_token(self) -> None:
        """Test masking of short tokens returns ***."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        assert api._mask_token("short") == "***"
        assert api._mask_token("12345678") == "***"


class TestRoamAPICall:
    """Tests for RoamAPI.call method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_success(self, mock_post: MagicMock) -> None:
        """Test successful API call."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.call("/api/graph/test-graph/q", {"query": "test"})

        assert result == mock_response
        mock_post.assert_called_once()

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_redirect(self, mock_post: MagicMock) -> None:
        """Test API call with redirect."""
        # First call returns redirect
        redirect_response = MagicMock()
        redirect_response.is_redirect = True
        redirect_response.status_code = 307
        redirect_response.headers = {
            "Location": "https://peer-123.api.roamresearch.com:8765/api/graph/test"
        }

        # Second call succeeds
        success_response = MagicMock()
        success_response.ok = True
        success_response.is_redirect = False
        success_response.status_code = 200

        mock_post.side_effect = [redirect_response, success_response]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.call("/api/graph/test-graph/q", {"query": "test"})

        assert result == success_response
        assert mock_post.call_count == 2
        assert api._redirect_cache["test-graph"] == (
            "https://peer-123.api.roamresearch.com:8765"
        )

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_redirect_no_location(self, mock_post: MagicMock) -> None:
        """Test error when redirect has no Location header."""
        redirect_response = MagicMock()
        redirect_response.is_redirect = True
        redirect_response.status_code = 307
        redirect_response.headers = {}

        mock_post.return_value = redirect_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api.call("/api/graph/test-graph/q", {"query": "test"})
        assert "Redirect without Location header" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_redirect_invalid_url(self, mock_post: MagicMock) -> None:
        """Test error when redirect URL cannot be parsed."""
        redirect_response = MagicMock()
        redirect_response.is_redirect = True
        redirect_response.status_code = 307
        redirect_response.headers = {"Location": "https://invalid-url.com/api"}

        mock_post.return_value = redirect_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api.call("/api/graph/test-graph/q", {"query": "test"})
        assert "Could not parse redirect URL" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_error_500(self, mock_post: MagicMock) -> None:
        """Test error handling for HTTP 500."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 500
        error_response.text = "Internal Server Error"

        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(RoamAPIError) as exc_info:
            api.call("/api/graph/test-graph/q", {"query": "test"})
        assert "Server error (HTTP 500)" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_error_400(self, mock_post: MagicMock) -> None:
        """Test error handling for HTTP 400."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 400
        error_response.text = "Bad Request"

        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(InvalidQueryError) as exc_info:
            api.call("/api/graph/test-graph/q", {"query": "test"})
        assert "Bad request (HTTP 400)" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_error_401(self, mock_post: MagicMock) -> None:
        """Test error handling for HTTP 401."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 401
        error_response.text = "Unauthorized"

        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(AuthenticationError) as exc_info:
            api.call("/api/graph/test-graph/q", {"query": "test"})
        assert "Authentication error (HTTP 401)" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_error_429(self, mock_post: MagicMock) -> None:
        """Test error handling for HTTP 429 (rate limit)."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 429
        error_response.text = "Too Many Requests"

        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(RateLimitError) as exc_info:
            api.call("/api/graph/test-graph/q", {"query": "test"})
        assert "Rate limit exceeded (HTTP 429)" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_call_error_other(self, mock_post: MagicMock) -> None:
        """Test error handling for other HTTP errors."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 503
        error_response.text = "Service Unavailable"

        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(RoamAPIError) as exc_info:
            api.call("/api/graph/test-graph/q", {"query": "test"})
        assert "Service unavailable (HTTP 503)" in str(exc_info.value)


class TestRunQuery:
    """Tests for RoamAPI.run_query method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_run_query_success(self, mock_post: MagicMock) -> None:
        """Test successful query execution."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [[1, "test"]]}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.run_query("[:find ?e :where ...]")

        assert result == [[1, "test"]]

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_run_query_with_args(self, mock_post: MagicMock) -> None:
        """Test query execution with arguments."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [[1]]}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.run_query("[:find ?e :in $ ?title :where ...]", {"?title": "Test"})

        assert result == [[1]]
        call_args = mock_post.call_args
        assert call_args[1]["json"]["args"] == {"?title": "Test"}


class TestPull:
    """Tests for RoamAPI.pull method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_pull_success(self, mock_post: MagicMock) -> None:
        """Test successful pull."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {":block/string": "test", ":block/uid": "abc123"}
        }
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.pull("123")

        assert result == {":block/string": "test", ":block/uid": "abc123"}


class TestGetReferencesToPage:
    """Tests for RoamAPI.get_references_to_page method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_references_success(self, mock_post: MagicMock) -> None:
        """Test successful get references."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [["uid1", "Block with [[Test Page]]"]]
        }
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_references_to_page("Test Page")

        assert len(result) == 1
        assert result[0]["uid"] == "uid1"
        assert result[0]["string"] == "Block with [[Test Page]]"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_references_with_max_results(self, mock_post: MagicMock) -> None:
        """Test get references with max_results limit."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": [
                ["uid1", "Block 1"],
                ["uid2", "Block 2"],
                ["uid3", "Block 3"],
            ]
        }
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_references_to_page("Test Page", max_results=2)

        assert len(result) == 2

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_references_api_error(self, mock_post: MagicMock) -> None:
        """Test get references returns empty list on error."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.is_redirect = False
        mock_response.status_code = 500
        mock_response.text = "Error"
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_references_to_page("Test Page")

        assert result == []

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_references_auth_error_reraises(self, mock_post: MagicMock) -> None:
        """Test get references re-raises AuthenticationError."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 401
        error_response.text = "Unauthorized"
        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(AuthenticationError) as exc_info:
            api.get_references_to_page("Test Page")

        assert "Authentication error (HTTP 401)" in str(exc_info.value)

    def test_get_references_invalid_query_error_reraises(self) -> None:
        """Test get references re-raises InvalidQueryError for bad input."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        # Input with suspicious pattern should raise InvalidQueryError
        with pytest.raises(InvalidQueryError) as exc_info:
            api.get_references_to_page("[:find ?e :where ...")

        assert "suspicious pattern" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_references_rate_limit_returns_empty(
        self, mock_post: MagicMock
    ) -> None:
        """Test get references returns empty list on rate limit error."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 429
        error_response.text = "Too Many Requests"
        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_references_to_page("Test Page")

        # Rate limit error should be caught and return empty list
        assert result == []


class TestGetBlock:
    """Tests for RoamAPI.get_block method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_block_success(self, mock_post: MagicMock) -> None:
        """Test successful get block."""
        query_response = MagicMock()
        query_response.ok = True
        query_response.is_redirect = False
        query_response.status_code = 200
        query_response.json.return_value = {"result": [[123]]}

        pull_response = MagicMock()
        pull_response.ok = True
        pull_response.is_redirect = False
        pull_response.status_code = 200
        pull_response.json.return_value = {
            "result": {":block/string": "test", ":block/uid": "abc123"}
        }

        mock_post.side_effect = [query_response, pull_response]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_block("abc123")

        assert result[":block/string"] == "test"
        assert result[":block/uid"] == "abc123"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_block_not_found(self, mock_post: MagicMock) -> None:
        """Test get block when block not found."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(BlockNotFoundError) as exc_info:
            api.get_block("nonexistent")
        assert "nonexistent" in str(exc_info.value)


class TestGetPage:
    """Tests for RoamAPI.get_page method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_page_success(self, mock_post: MagicMock) -> None:
        """Test successful get page."""
        query_response = MagicMock()
        query_response.ok = True
        query_response.is_redirect = False
        query_response.status_code = 200
        query_response.json.return_value = {"result": [[123]]}

        pull_response = MagicMock()
        pull_response.ok = True
        pull_response.is_redirect = False
        pull_response.status_code = 200
        pull_response.json.return_value = {
            "result": {":node/title": "Test Page", ":block/children": []}
        }

        mock_post.side_effect = [query_response, pull_response]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_page("Test Page")

        assert result[":node/title"] == "Test Page"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_page_not_found(self, mock_post: MagicMock) -> None:
        """Test get page when page not found."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(PageNotFoundError) as exc_info:
            api.get_page("Nonexistent Page")
        assert "Nonexistent Page" in str(exc_info.value)


class TestCreateBlock:
    """Tests for RoamAPI.create_block method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_create_block_with_page_uid(self, mock_post: MagicMock) -> None:
        """Test create block with page UID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"uid": "new-block-uid"}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.create_block("Test content", page_uid="page-uid")

        assert result["uid"] == "new-block-uid"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_create_block_with_parent_uid(self, mock_post: MagicMock) -> None:
        """Test create block with parent UID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"uid": "new-block-uid"}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.create_block("Test content", parent_uid="parent-uid")

        assert result["uid"] == "new-block-uid"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_create_block_default_daily_notes(self, mock_post: MagicMock) -> None:
        """Test create block defaults to daily notes page."""
        # First call: find daily note page
        query_response1 = MagicMock()
        query_response1.ok = True
        query_response1.is_redirect = False
        query_response1.status_code = 200
        query_response1.json.return_value = {"result": [[123]]}

        # Second call: get daily note UID
        query_response2 = MagicMock()
        query_response2.ok = True
        query_response2.is_redirect = False
        query_response2.status_code = 200
        query_response2.json.return_value = {"result": [["daily-uid"]]}

        # Third call: create block
        create_response = MagicMock()
        create_response.ok = True
        create_response.is_redirect = False
        create_response.status_code = 200
        create_response.json.return_value = {"uid": "new-block-uid"}

        mock_post.side_effect = [query_response1, query_response2, create_response]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.create_block("Test content")

        assert result["uid"] == "new-block-uid"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_create_block_daily_note_not_found(self, mock_post: MagicMock) -> None:
        """Test error when daily notes page not found."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(PageNotFoundError) as exc_info:
            api.create_block("Test content")
        assert "Daily Notes page" in str(exc_info.value)

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_create_block_daily_uid_not_found(self, mock_post: MagicMock) -> None:
        """Test error when daily notes UID not found."""
        # First call finds the page
        query_response1 = MagicMock()
        query_response1.ok = True
        query_response1.is_redirect = False
        query_response1.status_code = 200
        query_response1.json.return_value = {"result": [[123]]}

        # Second call returns empty (no UID)
        query_response2 = MagicMock()
        query_response2.ok = True
        query_response2.is_redirect = False
        query_response2.status_code = 200
        query_response2.json.return_value = {"result": []}

        mock_post.side_effect = [query_response1, query_response2]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(BlockNotFoundError) as exc_info:
            api.create_block("Test content")
        assert "Could not find UID" in str(exc_info.value)


class TestFindDailyNoteFormat:
    """Tests for RoamAPI.find_daily_note_format method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_find_format_cached(self, mock_post: MagicMock) -> None:
        """Test that cached format is returned without API calls."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        api._daily_note_format = "%B %d, %Y"

        result = api.find_daily_note_format()

        assert result == "%B %d, %Y"
        mock_post.assert_not_called()

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_find_format_first_match(self, mock_post: MagicMock) -> None:
        """Test finding format on first try."""
        # First format succeeds
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [[123]]}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.find_daily_note_format()

        assert result == "%B %d, %Y"
        assert api._daily_note_format == "%B %d, %Y"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_find_format_ordinal(self, mock_post: MagicMock) -> None:
        """Test finding ordinal format like 'June 13th, 2025'."""
        # First format fails, second succeeds (ordinal)
        fail_response = MagicMock()
        fail_response.ok = True
        fail_response.is_redirect = False
        fail_response.status_code = 200
        fail_response.json.return_value = {"result": []}

        success_response = MagicMock()
        success_response.ok = True
        success_response.is_redirect = False
        success_response.status_code = 200
        success_response.json.return_value = {"result": [[123]]}

        mock_post.side_effect = [fail_response, success_response]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.find_daily_note_format()

        assert result == "%B %dth, %Y"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_find_format_no_match(self, mock_post: MagicMock) -> None:
        """Test fallback when no format matches."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.is_redirect = False
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.find_daily_note_format()

        # Should fall back to default
        assert result == "%m-%d-%Y"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_find_format_exception_continues(self, mock_post: MagicMock) -> None:
        """Test that exceptions during format detection are handled."""

        def create_empty_response() -> MagicMock:
            resp = MagicMock()
            resp.ok = True
            resp.is_redirect = False
            resp.status_code = 200
            resp.json.return_value = {"result": []}
            return resp

        def create_error_response() -> MagicMock:
            resp = MagicMock()
            resp.ok = False
            resp.is_redirect = False
            resp.status_code = 500
            resp.text = "Internal Server Error"
            return resp

        # First call returns server error, rest return empty
        mock_post.side_effect = [create_error_response()] + [
            create_empty_response() for _ in range(15)
        ]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.find_daily_note_format()

        # Should fall back to default after all attempts
        assert result == "%m-%d-%Y"

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_find_format_auth_error_reraises(self, mock_post: MagicMock) -> None:
        """Test that AuthenticationError during format detection is re-raised."""
        error_response = MagicMock()
        error_response.ok = False
        error_response.is_redirect = False
        error_response.status_code = 401
        error_response.text = "Unauthorized"
        mock_post.return_value = error_response

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        with pytest.raises(AuthenticationError) as exc_info:
            api.find_daily_note_format()

        assert "Authentication error (HTTP 401)" in str(exc_info.value)


class TestGetDailyNotesContext:
    """Tests for RoamAPI.get_daily_notes_context method."""

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_context_with_content(self, mock_post: MagicMock) -> None:
        """Test getting daily notes context with content."""
        # Mock format detection (first call)
        format_response = MagicMock()
        format_response.ok = True
        format_response.is_redirect = False
        format_response.status_code = 200
        format_response.json.return_value = {"result": [[123]]}

        # Mock page query response
        page_query_response = MagicMock()
        page_query_response.ok = True
        page_query_response.is_redirect = False
        page_query_response.status_code = 200
        page_query_response.json.return_value = {"result": [[456]]}

        # Mock page pull response
        page_pull_response = MagicMock()
        page_pull_response.ok = True
        page_pull_response.is_redirect = False
        page_pull_response.status_code = 200
        page_pull_response.json.return_value = {
            "result": {
                ":node/title": "December 15, 2025",
                ":block/children": [
                    {":block/string": "Test note", ":block/uid": "uid1"}
                ],
            }
        }

        # Mock references query
        refs_response = MagicMock()
        refs_response.ok = True
        refs_response.is_redirect = False
        refs_response.status_code = 200
        refs_response.json.return_value = {
            "result": [["ref-uid", "Reference to [[December 15, 2025]]"]]
        }

        mock_post.side_effect = [
            format_response,
            page_query_response,
            page_pull_response,
            refs_response,
        ]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_daily_notes_context(days=1, max_references=10)

        assert "Daily Notes Context" in result
        assert "Test note" in result

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_context_page_not_found(self, mock_post: MagicMock) -> None:
        """Test handling when daily note page not found."""
        # Mock format detection
        format_response = MagicMock()
        format_response.ok = True
        format_response.is_redirect = False
        format_response.status_code = 200
        format_response.json.return_value = {"result": [[123]]}

        # Mock page query returns empty (page not found)
        page_response = MagicMock()
        page_response.ok = True
        page_response.is_redirect = False
        page_response.status_code = 200
        page_response.json.return_value = {"result": []}

        mock_post.side_effect = [format_response, page_response]

        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        result = api.get_daily_notes_context(days=1, max_references=10)

        assert "No daily notes found" in result

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_context_ordinal_format(self, mock_post: MagicMock) -> None:
        """Test getting context with ordinal date format."""
        # Set cached format to ordinal
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        api._daily_note_format = "%B %dth, %Y"

        # Mock page not found for simpler test
        page_response = MagicMock()
        page_response.ok = True
        page_response.is_redirect = False
        page_response.status_code = 200
        page_response.json.return_value = {"result": []}

        mock_post.return_value = page_response

        result = api.get_daily_notes_context(days=1, max_references=10)

        assert "No daily notes found" in result

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_context_empty_children(self, mock_post: MagicMock) -> None:
        """Test context when page has empty children list."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        api._daily_note_format = "%B %d, %Y"

        # Mock page query response
        page_query_response = MagicMock()
        page_query_response.ok = True
        page_query_response.is_redirect = False
        page_query_response.status_code = 200
        page_query_response.json.return_value = {"result": [[456]]}

        # Mock page pull with empty children
        page_pull_response = MagicMock()
        page_pull_response.ok = True
        page_pull_response.is_redirect = False
        page_pull_response.status_code = 200
        page_pull_response.json.return_value = {
            "result": {":node/title": "December 15, 2025", ":block/children": []}
        }

        # Mock empty references
        refs_response = MagicMock()
        refs_response.ok = True
        refs_response.is_redirect = False
        refs_response.status_code = 200
        refs_response.json.return_value = {"result": []}

        mock_post.side_effect = [page_query_response, page_pull_response, refs_response]

        result = api.get_daily_notes_context(days=1, max_references=10)

        # Page found but no content - should return "No daily notes found"
        assert "No daily notes found" in result

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_context_empty_block_strings(self, mock_post: MagicMock) -> None:
        """Test context when page has children with empty strings."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        api._daily_note_format = "%B %d, %Y"

        # Mock page query response
        page_query_response = MagicMock()
        page_query_response.ok = True
        page_query_response.is_redirect = False
        page_query_response.status_code = 200
        page_query_response.json.return_value = {"result": [[456]]}

        # Mock page with children that have empty strings
        page_pull_response = MagicMock()
        page_pull_response.ok = True
        page_pull_response.is_redirect = False
        page_pull_response.status_code = 200
        page_pull_response.json.return_value = {
            "result": {
                ":node/title": "December 15, 2025",
                ":block/children": [{":block/string": "", ":block/uid": "uid1"}],
            }
        }

        # Mock empty references
        refs_response = MagicMock()
        refs_response.ok = True
        refs_response.is_redirect = False
        refs_response.status_code = 200
        refs_response.json.return_value = {"result": []}

        mock_post.side_effect = [page_query_response, page_pull_response, refs_response]

        result = api.get_daily_notes_context(days=1, max_references=10)

        # Empty strings produce no markdown, no references - no daily notes
        assert "No daily notes found" in result

    @patch("mcp_server_roam.roam_api.requests.post")
    def test_get_context_no_references(self, mock_post: MagicMock) -> None:
        """Test context when page has content but no references."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        api._daily_note_format = "%B %d, %Y"

        # Mock page query response
        page_query_response = MagicMock()
        page_query_response.ok = True
        page_query_response.is_redirect = False
        page_query_response.status_code = 200
        page_query_response.json.return_value = {"result": [[456]]}

        # Mock page with actual content
        page_pull_response = MagicMock()
        page_pull_response.ok = True
        page_pull_response.is_redirect = False
        page_pull_response.status_code = 200
        page_pull_response.json.return_value = {
            "result": {
                ":node/title": "December 15, 2025",
                ":block/children": [
                    {":block/string": "Some content", ":block/uid": "uid1"}
                ],
            }
        }

        # Mock empty references
        refs_response = MagicMock()
        refs_response.ok = True
        refs_response.is_redirect = False
        refs_response.status_code = 200
        refs_response.json.return_value = {"result": []}

        mock_post.side_effect = [page_query_response, page_pull_response, refs_response]

        result = api.get_daily_notes_context(days=1, max_references=10)

        # Should have content but no references section
        assert "Daily Notes Context" in result
        assert "Some content" in result
        assert "References to" not in result


class TestProcessBlocks:
    """Tests for RoamAPI.process_blocks method."""

    def test_process_simple_blocks(self) -> None:
        """Test processing simple blocks."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        blocks = [
            {":block/string": "First block", ":block/uid": "uid1"},
            {":block/string": "Second block", ":block/uid": "uid2"},
        ]

        result = api.process_blocks(blocks)

        assert "- First block\n" in result
        assert "- Second block\n" in result

    def test_process_nested_blocks(self) -> None:
        """Test processing nested blocks."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        blocks = [
            {
                ":block/string": "Parent",
                ":block/uid": "uid1",
                ":block/children": [
                    {":block/string": "Child", ":block/uid": "uid2"},
                ],
            },
        ]

        result = api.process_blocks(blocks)

        assert "- Parent\n" in result
        assert "  - Child\n" in result

    def test_process_blocks_skip_empty(self) -> None:
        """Test that empty blocks are skipped."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        blocks = [
            {":block/string": "", ":block/uid": "uid1"},
            {":block/string": "Not empty", ":block/uid": "uid2"},
        ]

        result = api.process_blocks(blocks)

        assert "- Not empty\n" in result
        assert result.count("-") == 1

    def test_process_blocks_extract_links(self) -> None:
        """Test extracting links from blocks."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        blocks = [
            {":block/string": "Link to [[Page A]]", ":block/uid": "uid1"},
            {
                ":block/string": "Link to [[Page B]] and [[Page C]]",
                ":block/uid": "uid2",
            },
        ]
        linked_pages: set[str] = set()

        api.process_blocks(blocks, extract_links=True, linked_pages=linked_pages)

        assert "Page A" in linked_pages
        assert "Page B" in linked_pages
        assert "Page C" in linked_pages
        assert len(linked_pages) == 3

    def test_process_blocks_extract_links_missing_param(self) -> None:
        """Test error when extract_links=True but linked_pages not provided."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        blocks = [{":block/string": "Test", ":block/uid": "uid1"}]

        with pytest.raises(ValueError) as exc_info:
            api.process_blocks(blocks, extract_links=True)
        assert "linked_pages parameter is required" in str(exc_info.value)

    def test_process_blocks_with_depth(self) -> None:
        """Test processing blocks at specific depth."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")
        blocks = [{":block/string": "Test", ":block/uid": "uid1"}]

        result = api.process_blocks(blocks, depth=2)

        assert "    - Test\n" in result  # 4 spaces = depth 2


class TestExceptionClasses:
    """Tests for custom exception classes."""

    def test_roam_api_error(self) -> None:
        """Test RoamAPIError is base class."""
        error = RoamAPIError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_page_not_found_error(self) -> None:
        """Test PageNotFoundError inherits from RoamAPIError."""
        error = PageNotFoundError("Page not found")
        assert isinstance(error, RoamAPIError)

    def test_block_not_found_error(self) -> None:
        """Test BlockNotFoundError inherits from RoamAPIError."""
        error = BlockNotFoundError("Block not found")
        assert isinstance(error, RoamAPIError)

    def test_authentication_error(self) -> None:
        """Test AuthenticationError inherits from RoamAPIError."""
        error = AuthenticationError("Auth failed")
        assert isinstance(error, RoamAPIError)

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError inherits from RoamAPIError."""
        error = RateLimitError("Rate limited")
        assert isinstance(error, RoamAPIError)

    def test_invalid_query_error(self) -> None:
        """Test InvalidQueryError inherits from RoamAPIError."""
        error = InvalidQueryError("Invalid query")
        assert isinstance(error, RoamAPIError)


class TestBulkFetchMethods:
    """Tests for bulk fetch methods used by sync_index."""

    def test_get_all_blocks_for_sync_success(self) -> None:
        """Test fetching all blocks for sync."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        mock_results = [
            ["uid1", "content 1", 1000, "page-uid-1", "Page 1"],
            ["uid2", "content 2", 2000, "page-uid-2", "Page 2"],
        ]

        with patch.object(api, "run_query", return_value=mock_results) as mock_query:
            blocks = api.get_all_blocks_for_sync()

            assert len(blocks) == 2
            assert blocks[0] == {
                "uid": "uid1",
                "content": "content 1",
                "edit_time": 1000,
                "page_uid": "page-uid-1",
                "page_title": "Page 1",
            }
            assert blocks[1]["uid"] == "uid2"
            mock_query.assert_called_once()

    def test_get_all_blocks_for_sync_empty(self) -> None:
        """Test fetching all blocks when none exist."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with patch.object(api, "run_query", return_value=[]):
            blocks = api.get_all_blocks_for_sync()
            assert blocks == []

    def test_get_blocks_modified_since_success(self) -> None:
        """Test fetching blocks modified since a timestamp."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        mock_results = [
            ["uid1", "content 1", 2000, "page-uid-1", "Page 1"],
        ]

        with patch.object(api, "run_query", return_value=mock_results) as mock_query:
            blocks = api.get_blocks_modified_since(1500)

            assert len(blocks) == 1
            assert blocks[0]["uid"] == "uid1"
            # Verify the query includes the timestamp filter
            query_arg = mock_query.call_args[0][0]
            assert "1500" in query_arg

    def test_get_blocks_modified_since_empty(self) -> None:
        """Test fetching modified blocks when none exist."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with patch.object(api, "run_query", return_value=[]):
            blocks = api.get_blocks_modified_since(1500)
            assert blocks == []

    def test_get_block_parent_chain_success(self) -> None:
        """Test fetching parent chain for a block."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        mock_results = [
            ["Parent 1", 0],
            ["Parent 2", 1],
            ["Parent 3", 2],
        ]

        with patch.object(api, "run_query", return_value=mock_results):
            chain = api.get_block_parent_chain("block-uid")

            # Should be sorted by order
            assert chain == ["Parent 1", "Parent 2", "Parent 3"]

    def test_get_block_parent_chain_empty(self) -> None:
        """Test fetching parent chain when block has no parents."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with patch.object(api, "run_query", return_value=[]):
            chain = api.get_block_parent_chain("block-uid")
            assert chain == []

    def test_get_block_parent_chain_api_error(self) -> None:
        """Test parent chain returns empty on API error."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with patch.object(api, "run_query", side_effect=RoamAPIError("API Error")):
            chain = api.get_block_parent_chain("block-uid")
            assert chain == []


class TestSearchBlocksByText:
    """Tests for search_blocks_by_text method."""

    def test_search_blocks_by_text_success(self) -> None:
        """Test successful text search."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        mock_results = [
            ["uid1", "First block content", "Page 1"],
            ["uid2", "Second block content", "Page 2"],
        ]

        with patch.object(api, "run_query", return_value=mock_results):
            results = api.search_blocks_by_text("block")

            assert len(results) == 2
            assert results[0]["uid"] == "uid1"
            assert results[0]["content"] == "First block content"
            assert results[0]["page_title"] == "Page 1"
            assert results[1]["uid"] == "uid2"

    def test_search_blocks_by_text_with_page_filter(self) -> None:
        """Test text search with page filter."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        mock_results = [
            ["uid1", "Filtered content", "Specific Page"],
        ]

        with patch.object(api, "run_query", return_value=mock_results) as mock_query:
            results = api.search_blocks_by_text("content", page_title="Specific Page")

            assert len(results) == 1
            # Verify the query includes the page filter
            call_args = mock_query.call_args[0][0]
            assert "Specific Page" in call_args

    def test_search_blocks_by_text_with_limit(self) -> None:
        """Test text search respects limit."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        mock_results = [
            ["uid1", "Content 1", "Page 1"],
            ["uid2", "Content 2", "Page 2"],
            ["uid3", "Content 3", "Page 3"],
        ]

        with patch.object(api, "run_query", return_value=mock_results):
            results = api.search_blocks_by_text("Content", limit=2)

            assert len(results) == 2
            assert results[0]["uid"] == "uid1"
            assert results[1]["uid"] == "uid2"

    def test_search_blocks_by_text_empty_results(self) -> None:
        """Test text search with no results."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with patch.object(api, "run_query", return_value=[]):
            results = api.search_blocks_by_text("nonexistent")
            assert results == []

    def test_search_blocks_by_text_api_error(self) -> None:
        """Test text search returns empty on API error."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with patch.object(api, "run_query", side_effect=RoamAPIError("API Error")):
            results = api.search_blocks_by_text("query")
            assert results == []

    def test_search_blocks_by_text_auth_error_raises(self) -> None:
        """Test text search raises on authentication error."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with (
            patch.object(
                api, "run_query", side_effect=AuthenticationError("Auth failed")
            ),
            pytest.raises(AuthenticationError),
        ):
            api.search_blocks_by_text("query")

    def test_search_blocks_by_text_invalid_query_raises(self) -> None:
        """Test text search raises on invalid query error."""
        api = RoamAPI(api_token="test-token", graph_name="test-graph")

        with (
            patch.object(api, "run_query", side_effect=InvalidQueryError("Invalid")),
            pytest.raises(InvalidQueryError),
        ):
            api.search_blocks_by_text("[:find")
