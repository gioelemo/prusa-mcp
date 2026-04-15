"""Entry point for `python -m prusa_mcp` and the `prusa-mcp` CLI.

Subcommands:
    (no args)   Run the MCP server over stdio (default).
    login       Run the interactive OAuth2 login against Prusa Account
                and persist tokens to disk.
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    """Dispatch to the MCP server or the login helper."""
    parser = argparse.ArgumentParser(prog="prusa-mcp", description="Prusa Connect MCP server")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("login", help="Authenticate with Prusa Account (OAuth2 PKCE)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "login":
        # Local import so `prusa-mcp` (no args) doesn't pay the import cost.
        from prusa_mcp.oauth import login_interactive  # noqa: PLC0415

        try:
            login_interactive()
        except RuntimeError as e:
            print(f"Login failed: {e}", file=sys.stderr)
            sys.exit(1)
        print("Login successful. Tokens saved.")
        return

    # Default: run the MCP server.
    from prusa_mcp.server import main as run_server  # noqa: PLC0415

    run_server()


if __name__ == "__main__":
    main()
