"""Command line interface for TrimTank."""

from __future__ import annotations

import argparse
from importlib import metadata
from typing import Sequence

from . import __version__


PACKAGE_NAME = "trimtank"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8145


def get_version() -> str:
    """Return the installed package version, falling back for source runs."""
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trimtank",
        description="Prepare local image datasets for LoRA training workflows.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the TrimTank version and exit.",
    )

    subparsers = parser.add_subparsers(dest="command")
    start_parser = subparsers.add_parser(
        "start",
        help="Start the local TrimTank web app.",
    )
    start_parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host/interface to bind. Default: {DEFAULT_HOST}",
    )
    start_parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        type=_port,
        help=f"Port to serve on. Default: {DEFAULT_PORT}",
    )
    start_parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable development mode.",
    )
    start_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"TrimTank {get_version()}")
        return 0

    if args.command == "start":
        return _start(args)

    parser.print_help()
    return 0


def _start(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    verbose = args.verbose or args.dev
    log_level = "debug" if verbose else "info"
    app = create_app(dev=args.dev)

    uvicorn.run(app, host=args.host, port=args.port, log_level=log_level)
    return 0


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")

    return port
