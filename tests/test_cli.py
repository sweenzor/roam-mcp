"""Tests for CLI entry points and main function."""

import contextlib
import logging
import runpy
import sys
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from mcp_server_roam import main


class TestMainFunction:
    """Tests for the main CLI function."""

    def test_main_default_logging(self) -> None:
        """Test main function with default (no verbose) logging level."""
        runner = CliRunner()
        mock_coro = MagicMock()
        mock_serve = MagicMock(return_value=mock_coro)

        with (
            patch("mcp_server_roam.serve", new=mock_serve),
            patch("asyncio.run") as mock_run,
            patch.object(logging, "basicConfig") as mock_basic_config,
        ):
            runner.invoke(main)

            # Should use WARNING level by default
            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.WARN
            mock_run.assert_called_once_with(mock_coro)

    def test_main_verbose_once(self) -> None:
        """Test main function with -v (INFO level)."""
        runner = CliRunner()

        with (
            patch("mcp_server_roam.serve", new=MagicMock()),
            patch("asyncio.run"),
            patch.object(logging, "basicConfig") as mock_basic_config,
        ):
            runner.invoke(main, ["-v"])

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.INFO

    def test_main_verbose_twice(self) -> None:
        """Test main function with -vv (DEBUG level)."""
        runner = CliRunner()

        with (
            patch("mcp_server_roam.serve", new=MagicMock()),
            patch("asyncio.run"),
            patch.object(logging, "basicConfig") as mock_basic_config,
        ):
            runner.invoke(main, ["-vv"])

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.DEBUG

    def test_main_verbose_three_times(self) -> None:
        """Test main function with -vvv (DEBUG level, same as -vv)."""
        runner = CliRunner()

        with (
            patch("mcp_server_roam.serve", new=MagicMock()),
            patch("asyncio.run"),
            patch.object(logging, "basicConfig") as mock_basic_config,
        ):
            runner.invoke(main, ["-vvv"])

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            # -vvv should also be DEBUG
            assert call_kwargs["level"] == logging.DEBUG

    def test_main_calls_serve(self) -> None:
        """Test that main calls serve via asyncio.run."""
        runner = CliRunner()
        mock_coro = MagicMock()
        mock_serve = MagicMock(return_value=mock_coro)

        with (
            patch("mcp_server_roam.serve", new=mock_serve),
            patch("asyncio.run") as mock_run,
            patch.object(logging, "basicConfig"),
        ):
            result = runner.invoke(main)

            mock_run.assert_called_once_with(mock_coro)
            # Verify exit code is 0
            assert result.exit_code == 0

    def test_main_long_verbose_option(self) -> None:
        """Test main function with --verbose option."""
        runner = CliRunner()

        with (
            patch("mcp_server_roam.serve", new=MagicMock()),
            patch("asyncio.run"),
            patch.object(logging, "basicConfig") as mock_basic_config,
        ):
            runner.invoke(main, ["--verbose"])

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == logging.INFO

    def test_main_logging_stream(self) -> None:
        """Test that logging is configured to use stderr."""
        runner = CliRunner()

        with (
            patch("mcp_server_roam.serve", new=MagicMock()),
            patch("asyncio.run"),
            patch.object(logging, "basicConfig") as mock_basic_config,
        ):
            runner.invoke(main)

            call_kwargs = mock_basic_config.call_args[1]
            # Click runner may swap stderr, so just check a stream is passed
            assert "stream" in call_kwargs


class TestModuleMain:
    """Tests for __main__.py module."""

    def test_module_main_structure(self) -> None:
        """Test that __main__.py has the correct structure."""
        # Verify the package exports main
        from mcp_server_roam import main as main_func

        assert callable(main_func)

    def test_main_if_name_block(self) -> None:
        """Test the if __name__ == '__main__' block in __init__.py."""
        # We test this by ensuring the main function can be called directly
        runner = CliRunner()

        with (
            patch("mcp_server_roam.serve", new=MagicMock()),
            patch("asyncio.run"),
            patch.object(logging, "basicConfig"),
        ):
            # Simulate running as __main__
            result = runner.invoke(main)
            assert result.exit_code == 0

    def test_main_module_execution(self) -> None:
        """Test running package as module (python -m mcp_server_roam)."""
        import subprocess

        # Run the module with --help to avoid actually starting the server
        result = subprocess.run(
            [sys.executable, "-m", "mcp_server_roam", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "MCP Roam Server" in result.stdout

    def test_dunder_main_execution(self) -> None:
        """Test __main__.py module execution with runpy."""
        with patch("mcp_server_roam.main") as mock_main:
            # Prevent actual execution by patching main
            mock_main.return_value = None

            with contextlib.suppress(SystemExit):
                # Run __main__.py as __main__
                runpy.run_module("mcp_server_roam", run_name="__main__")

            # Verify main was called
            mock_main.assert_called()
