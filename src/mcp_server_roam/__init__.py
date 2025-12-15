"""MCP server for Roam Research API integration."""
import logging
import sys

import click

from .roam_api import (
    AuthenticationError,
    BlockNotFoundError,
    InvalidQueryError,
    PageNotFoundError,
    RateLimitError,
    RoamAPI,
    RoamAPIError,
)
from .server import serve

__all__ = [
    'main',
    'serve',
    'RoamAPI',
    'RoamAPIError',
    'PageNotFoundError',
    'BlockNotFoundError',
    'AuthenticationError',
    'RateLimitError',
    'InvalidQueryError'
]


@click.command()
@click.option("-v", "--verbose", count=True)
def main(verbose: int) -> None:
    """Run the MCP Roam Server.

    Args:
        verbose: Verbosity level (0=WARN, 1=INFO, 2+=DEBUG).
    """
    import asyncio

    logging_level = logging.WARN
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(level=logging_level, stream=sys.stderr)
    asyncio.run(serve())


if __name__ == "__main__":  # pragma: no cover
    main()
