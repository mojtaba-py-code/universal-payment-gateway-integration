"""Command-line interface.

Small operational helpers:

* ``upgi serve`` — run the ASGI server (uvicorn).
* ``upgi generate-key`` — print a fresh base64 AES-256 master key for
  ``UPGI_SECRET_ENCRYPTION_KEY``.
* ``upgi openapi`` — dump the OpenAPI schema to stdout.
* ``upgi version`` — print the version.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys

from app import __version__


def _generate_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="upgi", description="Universal Payment Gateway Integration"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the ASGI server")
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "Interface to bind. Loopback by default: this process fronts "
            "encrypted provider credentials, so exposing it to the network is "
            "opt-in. The container image passes --host 0.0.0.0 explicitly."
        ),
    )
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    sub.add_parser("generate-key", help="Print a fresh AES-256 master key")
    sub.add_parser("openapi", help="Dump the OpenAPI schema")
    sub.add_parser("version", help="Print the version")

    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "generate-key":
        print(_generate_key())
        return 0
    if args.command == "openapi":
        from app.main import create_app

        print(json.dumps(create_app().openapi(), indent=2))
        return 0
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "app.main:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0
    return 1  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
