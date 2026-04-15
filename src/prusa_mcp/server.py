"""Prusa Connect MCP server — tools backed by OAuth2 Bearer auth.

Authentication is delegated to :mod:`prusa_mcp.oauth`: the MCP tools call
:func:`~prusa_mcp.oauth.get_access_token` before every request, which handles
loading tokens from disk and refreshing them silently. Interactive login
happens out-of-band via the ``prusa-mcp login`` CLI subcommand.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from prusa_mcp.oauth import get_access_token
from prusa_mcp.oauth import LoginRequired

# Initialize FastMCP server
mcp = FastMCP("prusa-printer")
logger = logging.getLogger(__name__)


# ----------------------------
# Constants
# ----------------------------
CONNECT_URL = os.environ.get("PRUSA_CONNECT_URL", "https://connect.prusa3d.com")
PRUSA_API_BASE = CONNECT_URL.rstrip("/") + "/app"


# ----------------------------
# HTTP helpers
# ----------------------------
async def _auth_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return request headers with a fresh Bearer token."""
    token = await get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


async def make_prusa_request(endpoint: str) -> dict[str, Any] | None:
    """GET a Prusa Connect ``/app`` endpoint and return parsed JSON (or ``None`` on error)."""
    url = f"{PRUSA_API_BASE}{endpoint}"
    try:
        headers = await _auth_headers()
    except LoginRequired:
        logger.exception("Not authenticated")
        return None

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError):
            logger.exception("API request failed for %s", url)
            return None


# ----------------------------
# Tools
# ----------------------------
@mcp.tool()
async def connect_login(email: str = "", password: str = "") -> str:  # noqa: ARG001
    """Report the Prusa Connect authentication status.

    The legacy ``email``/``password`` parameters are accepted for backwards
    compatibility but ignored: authentication now uses OAuth2 via the
    ``prusa-mcp login`` CLI subcommand, which must be run once from a shell
    that can open a browser (typically the host machine). Tokens are
    persisted to disk and refreshed automatically.
    """
    try:
        await get_access_token()
    except LoginRequired as e:
        return (
            "Not authenticated. Run `prusa-mcp login` (or `uv run prusa-mcp login`) "
            f"on a machine with a browser to authorize this server.\nDetails: {e}"
        )
    except (httpx.HTTPError, RuntimeError) as e:
        logger.exception("Token refresh failed")
        return f"Authentication check failed: {e!s}"
    return "Authenticated — Prusa Connect tokens are valid and ready to use."


@mcp.tool()
async def get_printers(limit: int = 10) -> str:
    """Get list of Prusa printers.

    Args:
        limit: Maximum number of printers to return (default: 10)
    """
    endpoint = f"/printers?limit={limit}"
    data = await make_prusa_request(endpoint)

    if not data:
        return "Unable to fetch printer data."

    printers = data.get("printers", [])
    logger.info(data)

    if not printers:
        return "No printers found."

    formatted_printers = [format_printer(printer) for printer in printers]
    return "\n---\n".join(formatted_printers)


@mcp.tool()
async def get_printer_status(printer_uuid: str) -> str:
    """Get detailed status of a specific printer.

    Args:
        printer_uuid: The UUID of the printer
    """
    endpoint = "/printers"
    data = await make_prusa_request(endpoint)

    if not data:
        return "Unable to fetch printer data."

    printers = data.get("printers", [])
    printer = None

    for p in printers:
        if p.get("uuid") == printer_uuid or p.get("name") == printer_uuid:
            printer = p
            break

    if not printer:
        return f"Printer with UUID/name '{printer_uuid}' not found."

    return format_printer(printer)


@mcp.tool()
async def get_printer_jobs(printer_uuid: str, limit: int = 5) -> str:
    """Get recent jobs for a specific printer.

    Args:
        printer_uuid: The UUID of the printer
        limit: Maximum number of jobs to return (default: 5)
    """
    endpoint = f"/printers/{printer_uuid}/jobs?limit={limit}"
    data = await make_prusa_request(endpoint)

    if not data:
        return f"Unable to fetch jobs for printer {printer_uuid}."

    jobs = data.get("jobs", []) or data.get("data", [])

    if not jobs:
        return "No jobs found for this printer."

    formatted_jobs = []
    for job in jobs:
        job_id = job.get("id", "Unknown")
        file_name = job.get("display_name") or job.get("file_name") or "Unknown"
        status = job.get("status") or job.get("state") or "Unknown"
        started = job.get("started_at") or job.get("start") or "Unknown"
        completed = job.get("completed_at") or "N/A"
        progress = job.get("progress", "N/A")

        # Prefer `preview_url` if provided by the API; otherwise try other common fields
        file_obj = job.get("file") or {}
        preview = (
            job.get("preview_url")
            or job.get("display_path")
            or job.get("display_url")
            or file_obj.get("preview_url")
            or file_obj.get("display_path")
            or file_obj.get("display_url")
            or job.get("thumbnail")
            or job.get("preview")
        )

        # Normalize preview to a full absolute URL.
        if preview:
            try:
                p = str(preview).strip()
                if p.startswith(("http://", "https://")):
                    preview = p
                elif p.startswith("//"):
                    preview = "https:" + p
                elif p.startswith("/app"):
                    preview = PRUSA_API_BASE.rstrip("/") + p[len("/app") :]
                elif p.startswith("/"):
                    preview = CONNECT_URL.rstrip("/") + p
                else:
                    preview = CONNECT_URL.rstrip("/") + "/" + p.lstrip("/")
            except (ValueError, AttributeError):
                pass

        job_info = f"""
Job ID: {job_id}
File: {file_name}
Status: {status}
Started: {started}
Completed: {completed}
Progress: {progress}%
"""
        formatted_jobs.append(job_info)

    return "\n---\n".join(formatted_jobs)


@mcp.tool()
async def get_printer_files(printer_uuid: str, limit: int = 100) -> str:
    """Get list of files for a given printer UUID.

    Args:
        printer_uuid: UUID of the printer to query.
        limit: optional limit for the API (not all endpoints support it).
    """
    endpoint = f"/printers/{printer_uuid}/files?limit={limit}"
    data = await make_prusa_request(endpoint)

    if not data:
        return f"Unable to fetch files for printer {printer_uuid}."

    files = data.get("files") or []
    if not files:
        return "No files found for this printer."

    lines: list[str] = []
    for f in files:
        name = f.get("display_name") or f.get("name")
        size = f.get("size")
        mtime = f.get("m_timestamp")
        ftype = f.get("type")
        path = f.get("display_path") or f.get("path")

        meta = f.get("meta") or {}
        est = meta.get("estimated_printing_time_normal_mode") or meta.get("estimated_print_time")

        lines.append(f"{name} ({ftype}) - {path} - size={size} bytes - mtime={mtime} - est={est}")

    return "\n".join(lines)


@mcp.tool()
async def get_printer_storages(printer_uuid: str) -> str:
    """Get storage devices for a given printer UUID.

    Args:
        printer_uuid: UUID of the printer to query.
    """
    endpoint = f"/printers/{printer_uuid}/storages"
    data = await make_prusa_request(endpoint)

    if not data:
        return f"Unable to fetch storages for printer {printer_uuid}."

    storages = data.get("storages") or []
    if not storages:
        return "No storages found for this printer."

    lines: list[str] = []
    for s in storages:
        name = s.get("name")
        mount = s.get("mountpoint")
        free = s.get("free_space")
        fcount = s.get("file_count")
        stype = s.get("type")
        ro = s.get("read_only")

        lines.append(f"{name} ({stype}) mounted at {mount} - free={free} bytes - files={fcount} - read_only={ro}")

    return "\n".join(lines)


@mcp.tool()
async def send_printer_command(printer_uuid: str, command: str, args: dict[str, Any] | None = None) -> str:
    """Send a command to a specific printer.

    Args:
        printer_uuid: The UUID of the printer
        command: Command name (e.g., "PAUSE_PRINT", "RESUME_PRINT", "SET_PRINTER_READY")
        args: Optional dictionary of command arguments

    Common Commands:
        - PAUSE_PRINT: Pause the current print
        - RESUME_PRINT: Resume a paused print
        - STOP_PRINT: Stop/cancel the current print
        - SET_PRINTER_READY: Mark printer as ready
        - CANCEL_PRINTER_READY: Unmark printer as ready
        - START_PRINT: Start a print (requires args: {"path": "/path/to/file.gcode"})
        - BEEP: Make the printer beep
        - RESET_PRINTER: Reset the printer
        - SET_NOZZLE_TEMPERATURE: Set nozzle temp (args: {"nozzle_temperature": 210})
        - SET_HEATBED_TEMPERATURE: Set bed temp (args: {"bed_temperature": 60})
        - LOAD_FILAMENT: Load filament (optional args: {"filament": "PLA"})
        - UNLOAD_FILAMENT: Unload filament
    """
    endpoint = f"/printers/{printer_uuid}/commands"

    payload: dict[str, Any] = {"command": command}
    if args:
        payload["args"] = args

    try:
        headers = await _auth_headers({"Content-Type": "application/json"})
    except LoginRequired as e:
        return f"Not authenticated: {e}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{PRUSA_API_BASE}{endpoint}"
            logger.info("Sending command to %s: %s", url, payload)

            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            return f"Command '{command}' sent successfully to printer {printer_uuid}.\nResponse: {json.dumps(result, indent=2)}"
    except httpx.HTTPStatusError as e:
        logger.exception("HTTP error sending command")
        return f"Failed to send command: HTTP {e.response.status_code} - {e.response.text}"
    except (httpx.RequestError, json.JSONDecodeError) as e:
        logger.exception("Error sending command")
        return f"Error sending command: {e!s}"


@mcp.tool()
async def get_printer_events(printer_uuid: str, limit: int = 100) -> str:
    """Fetch recent events for the given printer UUID and format them.

    Args:
        printer_uuid: Printer UUID
        limit: Maximum number of events to fetch
    """
    endpoint = f"/printers/{printer_uuid}/events?limit={limit}"
    data = await make_prusa_request(endpoint)

    if not data:
        return f"Unable to fetch events for printer {printer_uuid}."

    events = data.get("events") or []
    if not events:
        return "No recent events found for this printer."

    lines: list[str] = []
    for e in events:
        evt = e.get("event")
        state = e.get("state")
        source = e.get("source")
        created = e.get("created")
        server_time = e.get("server_time")
        data_field = e.get("data")

        data_repr = None
        if isinstance(data_field, dict):
            keys = [k for k in ("target_nozzle", "target_bed", "path", "size") if k in data_field]
            if keys:  # noqa: SIM108
                data_repr = ", ".join(f"{k}={data_field[k]}" for k in keys)
            else:
                data_repr = json.dumps(data_field)

        line = f"{evt} - {state} - source={source} - created={created} - server_time={server_time}"
        if data_repr:
            line += f" - data: {data_repr}"

        lines.append(line)

    return "\n".join(lines)


# ----------------------------
# Formatting helpers
# ----------------------------
def format_printer(printer: dict) -> str:
    """Format a printer object into a readable string."""
    status = f"""
Printer Name: {printer.get("name", "Unknown")}
Printer UUID: {printer.get("uuid", "Unknown")}
Status: {printer.get("printer_state", "Unknown")}
Connection: {printer.get("connect_state", "Unknown")}
Type: {printer.get("printer_type_name", "Unknown")}
Location: {printer.get("location", "Unknown")}
"""

    if "temp" in printer:
        temp = printer["temp"]
        status += f"""
Temperature (Nozzle): {temp.get("temp_nozzle", "N/A")}°C (Target: {temp.get("target_nozzle", "N/A")}°C)
Temperature (Bed): {temp.get("temp_bed", "N/A")}°C (Target: {temp.get("target_bed", "N/A")}°C)
"""

    if "job_info" in printer:
        job = printer["job_info"]
        status += f"""
Current Job: {job.get("display_name", "Unknown")}
Progress: {job.get("progress", "N/A")}%
Time Printing: {job.get("time_printing", 0)} seconds
Time Remaining: {job.get("time_remaining", 0)} seconds
"""

    return status


# ----------------------------
# Entry point
# ----------------------------
def main() -> None:
    """Initialize and run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
