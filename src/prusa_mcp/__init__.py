"""Prusa MCP Server — MCP server for Prusa Connect integration."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

try:
    __version__ = version("prusa-mcp")
except PackageNotFoundError:  # pragma: no cover — running from a source tree
    __version__ = "0.0.0"
