import click
import logging
import sys
from .server import serve
from .roam_api import (
    RoamAPI,
    RoamAPIException,
    PageNotFoundException,
    BlockNotFoundException,
    AuthenticationException,
    RateLimitException,
    InvalidQueryException
)

__all__ = [
    'main',
    'serve',
    'RoamAPI',
    'RoamAPIException',
    'PageNotFoundException',
    'BlockNotFoundException',
    'AuthenticationException',
    'RateLimitException',
    'InvalidQueryException'
]

@click.command()
@click.option("-v", "--verbose", count=True)
def main(verbose: bool) -> None:
    """MCP Roam Server - Roam Research functionality for MCP"""
    import asyncio

    logging_level = logging.WARN
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(level=logging_level, stream=sys.stderr)
    asyncio.run(serve())

if __name__ == "__main__":
    main()