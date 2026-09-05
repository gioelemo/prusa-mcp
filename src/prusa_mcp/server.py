"""Prusa Connect MCP server — tools backed by OAuth2 Bearer auth.

Authentication is delegated to :mod:`prusa_mcp.oauth`: the MCP tools call
:func:`~prusa_mcp.oauth.get_access_token` before every request, which handles
loading tokens from disk and refreshing them silently. Interactive login
happens out-of-band via the ``prusa-mcp login`` CLI subcommand.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import UTC
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, NamedTuple

import httpx2
from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

from prusa_mcp import __version__
from prusa_mcp.oauth import get_access_token
from prusa_mcp.oauth import LoginRequired

# Initialize the MCP server. Everything after ``name`` must be passed by keyword:
# MCP SDK v2 inserted ``title``/``description`` ahead of ``instructions`` in the
# positional order. ``version`` is also new — servers that omit it advertise an
# empty version string to clients.
mcp = MCPServer("prusa-printer", version=__version__)
logger = logging.getLogger(__name__)


# ----------------------------
# Constants
# ----------------------------
CONNECT_URL = os.environ.get("PRUSA_CONNECT_URL", "https://connect.prusa3d.com")
PRUSA_API_BASE = CONNECT_URL.rstrip("/") + "/app"

# Default Connect team id for uploads. It is NOT exposed by /api/v1/me or the
# printer list; read it once from the Connect web app upload URL
# (``/app/users/teams/<TEAM_ID>/uploads``) and set it here via env, or pass it
# per-call. Tools also attempt to auto-discover it from the printer detail.
DEFAULT_TEAM_ID = os.environ.get("PRUSA_TEAM_ID", "")

# PrusaSlicer CLI used for local slicing (STL -> g-code/bgcode). Override with
# the full binary path when it isn't on PATH, e.g. on macOS:
#   /Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer
PRUSASLICER_CLI = os.environ.get("PRUSASLICER_CLI", "prusa-slicer")

# Connect accepts an upload before the file has reached the printer, so
# START_PRINT has to wait for it to land on the printer's own storage.
FILE_APPEAR_TIMEOUT_SECONDS = 120.0
FILE_POLL_INTERVAL_SECONDS = 2.0

# A blocking dialog shows up a moment after START_PRINT, not instantly.
DIALOG_WAIT_SECONDS = 15.0
DIALOG_POLL_INTERVAL_SECONDS = 1.5

# Binary G-code files start with this; ASCII ones begin with a comment.
BGCODE_MAGIC = b"GCDE"


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
        logger.warning("Not authenticated; run `prusa-mcp login` and try again")
        return None

    async with httpx2.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except (httpx2.HTTPStatusError, httpx2.RequestError, json.JSONDecodeError):
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
    except (httpx2.HTTPError, RuntimeError) as e:
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


def _format_timestamp(value: Any) -> str:
    """Render a Unix timestamp as a readable UTC datetime."""
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError, OverflowError):
        return "Unknown"


def _format_duration(seconds: Any) -> str:
    """Render a second count as ``2h 43m 16s``."""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "Unknown"
    hours, rest = divmod(max(total, 0), 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


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

    jobs = data.get("jobs") or data.get("data") or []

    if not jobs:
        return "No jobs found for this printer."

    formatted_jobs = []
    for job in jobs:
        # The filename lives on the nested ``file`` object; the job itself only
        # carries the printer's 8.3 short path (``/usb/CUBE20~1.BGC``).
        file_obj = job.get("file") or {}
        name = file_obj.get("display_name") or file_obj.get("name") or job.get("path") or "Unknown"

        lines = [
            f"Job ID: {job.get('id', 'Unknown')}",
            f"File: {name}",
            f"Status: {job.get('state') or job.get('status') or 'Unknown'}",
            f"Started: {_format_timestamp(job.get('start'))}",
        ]
        start, end = job.get("start"), job.get("end")
        if end:
            lines.append(f"Ended: {_format_timestamp(end)}")
        if start and end:
            # Derived from the timestamps rather than the job's own
            # ``time_printing``: on a job that was stopped early Connect leaves
            # that field holding the *previous* job's value.
            lines.append(f"Duration: {_format_duration(end - start)}")
        # Only a running job reports progress; finished ones omit the field
        # entirely, so don't render a meaningless "N/A%".
        if job.get("progress") is not None:
            lines.append(f"Progress: {job['progress']}%")

        formatted_jobs.append("\n".join(lines))

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


async def _resolve_printer_file(printer_uuid: str, wanted: str) -> tuple[str | None, str]:
    """Resolve a file reference to the printer's own path.

    Accepts the printer path (``/usb/CUBE20~1.BGC``), the display path, or the
    display name (``cube20.bgcode``). Returns ``(path, problem)``; ``path`` is
    ``None`` when nothing matched or the reference was ambiguous.
    """
    data = await make_prusa_request(f"/printers/{printer_uuid}/files?limit=200")
    if data is None:
        return None, f"Unable to fetch files for printer {printer_uuid}."

    matches = [
        entry
        for entry in data.get("files") or []
        if wanted in (entry.get("path"), entry.get("display_path"), entry.get("display_name"), entry.get("name"))
    ]
    if not matches:
        return None, f"No file matching {wanted!r} on printer {printer_uuid}."
    if len(matches) > 1:
        listed = ", ".join(sorted(str(entry.get("path")) for entry in matches))
        return None, f"{wanted!r} matches {len(matches)} files ({listed}); pass the exact path instead."
    return matches[0].get("path"), ""


@mcp.tool()
async def delete_printer_file(printer_uuid: str, path: str) -> str:
    """Delete a file from a printer's storage. This cannot be undone.

    Args:
        printer_uuid: The UUID of the printer
        path: The file to delete, given either as the printer's own path
            (``/usb/CUBE20~1.BGC``) or as the display name (``cube20.bgcode``).
            A name matching more than one file is refused rather than guessed at.
    """
    resolved, problem = await _resolve_printer_file(printer_uuid, path)
    if not resolved:
        return problem

    result = await send_printer_command(printer_uuid, "DELETE_FILE", {"path": resolved})
    return f"DELETE_FILE {path} -> {resolved}\n{result}"


def _tool_sort_key(item: tuple[str, Any]) -> int:
    """Order tools numerically; Connect keys them as strings ("1".."5")."""
    number, _ = item
    return int(number) if number.isdigit() else 0


@mcp.tool()
async def get_printer_tools(printer_uuid: str) -> str:
    """Get the tools (extruders) of a printer: loaded material, nozzle and which is active.

    Multi-tool machines such as the XL carry a different filament per tool, so
    this is what tells you which tool to print a given material with.

    Args:
        printer_uuid: The UUID of the printer
    """
    data = await make_prusa_request(f"/printers/{printer_uuid}")
    if not data:
        return f"Unable to fetch tools for printer {printer_uuid}."

    tools = data.get("tools") or {}
    if not tools:
        return "This printer reports no per-tool information (single-tool machine)."

    lines: list[str] = []
    for number, tool in sorted(tools.items(), key=_tool_sort_key):
        # Connect reports an unloaded tool as the literal "---", not as null.
        material = (tool.get("material") or "").strip()
        if not material or material == "---":
            material = "empty"
        nozzle = tool.get("nozzle_diameter")
        temp = tool.get("temp")

        flags = [name for key, name in (("hardened", "hardened"), ("high_flow", "high-flow")) if tool.get(key)]
        if tool.get("active"):
            flags.insert(0, "ACTIVE")

        line = f"Tool {number}: {material} - nozzle {nozzle}mm - {temp}°C"
        if flags:
            line += f" [{', '.join(flags)}]"
        lines.append(line)

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
        # Connect expects command arguments under "kwargs"; sending "args"
        # is rejected with MISSING_COMMAND_ARGUMENT even when the key is present.
        payload["kwargs"] = args

    try:
        headers = await _auth_headers({"Content-Type": "application/json"})
    except LoginRequired as e:
        return f"Not authenticated: {e}"

    try:
        async with httpx2.AsyncClient(timeout=30.0) as client:
            url = f"{PRUSA_API_BASE}{endpoint}"
            logger.info("Sending command to %s: %s", url, payload)

            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            return f"Command '{command}' sent successfully to printer {printer_uuid}.\nResponse: {json.dumps(result, indent=2)}"
    except httpx2.HTTPStatusError as e:
        logger.exception("HTTP error sending command")
        return f"Failed to send command: HTTP {e.response.status_code} - {e.response.text}"
    except (httpx2.RequestError, json.JSONDecodeError) as e:
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
# Slicing + cloud upload (STL -> g-code -> printer, all via Prusa Connect)
# ----------------------------
def _slice_to_gcode(stl_path: str, config_ini: str, output_path: str = "") -> tuple[str, int, str]:
    """Slice an STL via the PrusaSlicer CLI. Returns ``(output_path, size, stl_name)``.

    Blocking (filesystem + subprocess); call via ``asyncio.to_thread`` from async
    tools so the event loop stays free. Raises ``FileNotFoundError`` when inputs
    are missing and ``RuntimeError`` on a missing CLI or slicer failure.
    """
    stl = Path(stl_path).expanduser()
    cfg = Path(config_ini).expanduser()
    if not stl.is_file():
        raise FileNotFoundError(f"STL not found: {stl}")
    if not cfg.is_file():
        raise FileNotFoundError(f"Config bundle not found: {cfg}")
    # The profile, not the filename, decides the encoding: PrusaSlicer honours
    # --output verbatim, so defaulting to .bgcode against a profile with
    # binary_gcode = 0 yields ASCII G-code wearing a .bgcode suffix, which the
    # printer can refuse. Take the default extension from the profile instead.
    out = Path(output_path).expanduser() if output_path else stl.with_suffix(_config_gcode_suffix(cfg))

    cli = shutil.which(PRUSASLICER_CLI) or PRUSASLICER_CLI
    cmd = [cli, "--load", str(cfg), "--export-gcode", "--output", str(out), str(stl)]
    logger.info("Slicing: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"PrusaSlicer CLI not found ('{PRUSASLICER_CLI}'). Install PrusaSlicer or set "
            "PRUSASLICER_CLI to its binary path."
        ) from e
    if proc.returncode != 0:
        raise RuntimeError(f"PrusaSlicer exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}")
    if not out.is_file():
        raise RuntimeError(
            f"Slicer reported success but produced no file at {out}; "
            f"check the profile's output/extension settings. {proc.stdout.strip()}"
        )

    # Trust the bytes over the filename, including when the caller chose the name.
    actual_binary = out.read_bytes()[:4] == BGCODE_MAGIC
    if actual_binary != (out.suffix.lower() == ".bgcode"):
        produced, expected = ("binary", ".bgcode") if actual_binary else ("ASCII", ".gcode")
        raise RuntimeError(
            f"{out.name} contains {produced} G-code but is named {out.suffix}; the printer may "
            f"reject it. Rename it to {expected}, or flip binary_gcode in the profile to match."
        )
    return str(out), out.stat().st_size, stl.name


def _config_gcode_suffix(config_ini: Path) -> str:
    """Return ``.bgcode`` or ``.gcode`` according to the profile's ``binary_gcode``.

    The bundle is a flat ``key = value`` ini; PrusaSlicer omits the key on
    profiles that predate binary G-code, where the answer is ASCII.
    """
    try:
        for line in config_ini.read_text(errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "binary_gcode":
                return ".bgcode" if value.strip() == "1" else ".gcode"
    except OSError:
        logger.debug("Could not read %s to determine gcode encoding", config_ini)
    return ".gcode"


def _read_file(file_path: str) -> tuple[str, int, bytes]:
    """Read a local file, returning ``(name, size, bytes)``.

    Blocking; call via ``asyncio.to_thread``. Raises ``FileNotFoundError`` when
    the path is not a regular file.
    """
    p = Path(file_path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    data = p.read_bytes()
    return p.name, len(data), data


async def _resolve_team_id(printer_uuid: str, team_id: str = "") -> str | None:
    """Resolve a team_id from the arg, the ``PRUSA_TEAM_ID`` env, or the printer detail."""
    if team_id:
        return team_id
    if DEFAULT_TEAM_ID:
        return DEFAULT_TEAM_ID
    data = await make_prusa_request(f"/printers/{printer_uuid}")
    if data:
        tid = data.get("team_id") or (data.get("printer") or {}).get("team_id")
        if tid:
            return str(tid)
    return None


async def _upload_bytes(name: str, size: int, data: bytes, team_id: str, printer_uuid: str) -> dict[str, Any]:
    """Two-step Connect cloud upload: register the file, then PUT the raw bytes.

    Returns the registration response, which includes the on-printer ``path``
    used by START_PRINT. Mirrors PrusaSlicer's ``PrusaConnectNew`` upload flow.
    """
    async with httpx2.AsyncClient(timeout=300.0) as client:
        # 1) Register the upload and reserve an id.
        reg = await client.post(
            f"{PRUSA_API_BASE}/users/teams/{team_id}/uploads",
            headers=await _auth_headers({"Content-Type": "application/json"}),
            json={"filename": name, "printer_uuid": printer_uuid, "size": size},
        )
        reg.raise_for_status()
        info = reg.json()
        upload_id = info.get("id")
        if upload_id is None:
            raise RuntimeError(f"Upload registration returned no 'id': {info}")

        # 2) PUT the raw file body. Send both the slicer's Content-Type and the
        #    web app's ``upload-size`` header for maximum server compatibility.
        put = await client.put(
            f"{PRUSA_API_BASE}/teams/{team_id}/files/raw",
            params={"upload_id": upload_id},
            headers=await _auth_headers({"Content-Type": "text/x.gcode", "upload-size": str(size)}),
            content=data,
        )
        put.raise_for_status()
    return info


@mcp.tool()
async def slice_stl(stl_path: str, config_ini: str, output_path: str = "") -> str:
    """Slice a local STL into printable g-code/bgcode with the PrusaSlicer CLI.

    Runs entirely on the machine hosting this server — no network needed, so it
    works on restricted networks. Requires a local PrusaSlicer install; set the
    ``PRUSASLICER_CLI`` env var to the binary if it isn't on PATH (macOS:
    ``/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer``).

    Args:
        stl_path: Path to the input ``.stl``.
        config_ini: Path to an exported PrusaSlicer config bundle
            (PrusaSlicer -> File -> Export -> Export Config) selecting the
            printer, filament and print settings.
        output_path: Optional output file. Defaults to the STL name with a
            ``.bgcode`` extension, beside the input.
    """
    try:
        out_path, size, stl_name = await asyncio.to_thread(_slice_to_gcode, stl_path, config_ini, output_path)
    except FileNotFoundError as e:
        return str(e)
    except RuntimeError as e:
        return f"Slicing failed: {e}"
    return f"Sliced {stl_name} -> {out_path} ({size} bytes)"


async def _printer_file_paths(printer_uuid: str) -> frozenset[str]:
    """Snapshot the paths currently on the printer, to spot what an upload adds."""
    data = await make_prusa_request(f"/printers/{printer_uuid}/files?limit=200")
    return frozenset(entry["path"] for entry in (data or {}).get("files") or [] if entry.get("path"))


async def _wait_for_printer_file(
    printer_uuid: str,
    *,
    size: int | None = None,
    exclude_paths: frozenset[str] = frozenset(),
    since: float = 0.0,
    timeout_seconds: float = FILE_APPEAR_TIMEOUT_SECONDS,
) -> str | None:
    """Wait for a just-uploaded file to land on the printer, returning its real path.

    The upload response's ``path`` is unusable for START_PRINT: the transfer is
    not instant, and the printer's FAT storage addresses files by 8.3 short name
    (``/usb/CUBE20~1.BGC``) while Connect reports the long one. Polling the
    printer's own file list solves both — its ``path`` is what START_PRINT
    resolves, and the entry's presence proves the transfer finished.

    Matching by *name* would be wrong. Uploading a name that already exists makes
    Connect store the new copy under a different one (``cube20.bgcode`` becomes
    ``cube20[1].bgcode``), so a name match finds the stale file and START_PRINT
    runs the previous upload. Identify the new file by what changed instead: a
    path that was not there before, or an entry modified since the upload began,
    preferring the newest and requiring the size to match when known.

    Returns ``None`` if nothing matching appeared before ``timeout_seconds`` —
    deliberately, since printing a stale file is worse than not printing.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        data = await make_prusa_request(f"/printers/{printer_uuid}/files?limit=200")

        candidates = [
            entry
            for entry in (data or {}).get("files") or []
            if entry.get("path")
            and (entry["path"] not in exclude_paths or (entry.get("m_timestamp") or 0) >= since)
            and (size is None or entry.get("size") == size)
        ]
        if candidates:
            return max(candidates, key=lambda entry: entry.get("m_timestamp") or 0)["path"]

        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(FILE_POLL_INTERVAL_SECONDS)


async def _auto_continue_dialog(printer_uuid: str, allowed_keys: set[str]) -> str | None:
    """Press ``Continue`` on a blocking dialog, but only for allow-listed keys.

    Dialogs carry a stable ``key`` (e.g. ``UNFINISHED_SELFTEST``). Only keys the
    caller named explicitly are confirmed: the same channel carries
    filament-runout, thermal-anomaly and crash-detected dialogs, where blindly
    confirming would turn a stopped printer into a damaged one.

    Returns a description of what happened, or ``None`` when no dialog appeared.
    """
    deadline = time.monotonic() + DIALOG_WAIT_SECONDS
    while True:
        data = await make_prusa_request(f"/printers/{printer_uuid}")
        dialog = (data or {}).get("dialog_info") or {}
        key = dialog.get("key")
        if key and key in allowed_keys and "Continue" in (dialog.get("buttons") or []):
            result = await send_printer_command(
                printer_uuid, "DIALOG_ACTION", {"dialog_id": dialog.get("id"), "button": "Continue"}
            )
            return f"Auto-confirmed dialog {key} (code {dialog.get('code')}): {result}"
        if key:
            return (
                f"Printer is showing dialog {key} (code {dialog.get('code')}): "
                f"{dialog.get('text') or ''} — not in auto_continue_dialogs, leaving it for a human."
            )
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(DIALOG_POLL_INTERVAL_SECONDS)


class _Upload(NamedTuple):
    """What identifies a freshly uploaded file on the printer afterwards.

    Connect renames a colliding filename, so the name is not a reliable handle;
    what the upload *added* to the printer's file list is.
    """

    size: int
    paths_before: frozenset[str]
    started_at: float


async def _start_uploaded_print(
    printer_uuid: str,
    upload: _Upload,
    *,
    auto_continue_dialogs: list[str] | None = None,
    tool_mapping: dict[str, list[int]] | None = None,
) -> str:
    """START_PRINT a freshly uploaded file once it lands, clearing allowed dialogs."""
    printer_path = await _wait_for_printer_file(
        printer_uuid,
        size=upload.size,
        exclude_paths=upload.paths_before,
        since=upload.started_at,
    )
    if not printer_path:
        return (
            f"The uploaded file has not appeared on the printer within "
            f"{FILE_APPEAR_TIMEOUT_SECONDS:.0f}s; not starting a print, since the only "
            f"other candidate would be an older file of the same name."
        )

    args: dict[str, Any] = {"path": printer_path}
    if tool_mapping:
        args["tool_mapping"] = tool_mapping

    result = await send_printer_command(printer_uuid, "START_PRINT", args)
    if auto_continue_dialogs:
        dialog_msg = await _auto_continue_dialog(printer_uuid, set(auto_continue_dialogs))
        if dialog_msg:
            result = f"{result}\n{dialog_msg}"
    return result


@mcp.tool()
async def upload_gcode(  # noqa: PLR0913
    file_path: str,
    printer_uuid: str,
    team_id: str = "",
    *,
    auto_continue_dialogs: list[str] | None = None,
    tool_mapping: dict[str, list[int]] | None = None,
    start_print: bool = False,
) -> str:
    """Upload a sliced g-code/bgcode file to a printer via the Prusa Connect cloud.

    Works where only Connect (not local PrusaLink) is reachable. Uploads to the
    printer's storage and, optionally, starts the print immediately.

    Args:
        file_path: Local path to the ``.bgcode``/``.gcode`` file.
        printer_uuid: Target printer UUID.
        team_id: Connect team id. Defaults to the ``PRUSA_TEAM_ID`` env var, or is
            auto-discovered from the printer when possible. (Find it in the
            Connect upload URL: ``/app/users/teams/<TEAM_ID>/uploads``.)
        auto_continue_dialogs: Dialog keys to confirm automatically when they
            block the print, e.g. ``["UNFINISHED_SELFTEST"]``. Empty by default:
            only keys named here are confirmed, because the same channel carries
            filament-runout, thermal-anomaly and crash-detected dialogs that must
            be seen by a human. Any other dialog is reported and left alone.
        tool_mapping: Remap the tools a multi-tool g-code asks for onto the
            printer's physical tools, e.g. ``{"1": [3]}`` to run a file authored
            for tool 1 on tool 3. Both sides are 1-based. Extra entries in a list
            are spool-join fallbacks. The printer *replaces* its whole mapping
            rather than merging, so map every tool the file uses, not just one.
        start_print: When true, issue START_PRINT for the uploaded file.
    """
    tid = await _resolve_team_id(printer_uuid, team_id)
    if not tid:
        return (
            "Could not determine team_id. Pass team_id=... or set PRUSA_TEAM_ID "
            "(find it in the Connect upload URL: /app/users/teams/<TEAM_ID>/uploads)."
        )

    try:
        name, size, data = await asyncio.to_thread(_read_file, file_path)
    except FileNotFoundError as e:
        return str(e)

    # Snapshot the printer's files first: it is what the upload *adds* that
    # identifies it afterwards, since Connect renames a colliding name.
    before = await _printer_file_paths(printer_uuid) if start_print else frozenset()
    since = time.time()

    try:
        info = await _upload_bytes(name, size, data, tid, printer_uuid)
    except LoginRequired as e:
        return f"Not authenticated: {e}"
    except httpx2.HTTPStatusError as e:
        return f"Upload failed: HTTP {e.response.status_code} - {e.response.text}"
    except (httpx2.RequestError, RuntimeError, OSError) as e:
        logger.exception("Upload failed")
        return f"Upload failed: {e!s}"

    msg = f"Uploaded {name} -> {info.get('path')} (state={info.get('state')}, id={info.get('id')})."
    if start_print:
        started = await _start_uploaded_print(
            printer_uuid,
            _Upload(size=size, paths_before=before, started_at=since),
            auto_continue_dialogs=auto_continue_dialogs,
            tool_mapping=tool_mapping,
        )
        msg = f"{msg}\n{started}"
    return msg


@mcp.tool()
async def slice_and_print(  # noqa: PLR0913
    stl_path: str,
    printer_uuid: str,
    config_ini: str,
    team_id: str = "",
    *,
    auto_continue_dialogs: list[str] | None = None,
    tool_mapping: dict[str, list[int]] | None = None,
    start_print: bool = True,
) -> str:
    """One-shot: slice an STL locally, upload it to Connect, and optionally print.

    Combines :func:`slice_stl` and :func:`upload_gcode`. The entire network
    portion is Connect-only, so it works on restricted networks.

    Args:
        stl_path: Path to the input ``.stl``.
        printer_uuid: Target printer UUID.
        config_ini: Exported PrusaSlicer config bundle (see :func:`slice_stl`).
        team_id: Connect team id (see :func:`upload_gcode`).
        auto_continue_dialogs: Dialog keys to confirm automatically
            (see :func:`upload_gcode`). Empty by default.
        tool_mapping: Remap g-code tools onto physical tools
            (see :func:`upload_gcode`).
        start_print: When true (default), START_PRINT after upload.
    """
    try:
        out_path, _size, _name = await asyncio.to_thread(_slice_to_gcode, stl_path, config_ini)
    except FileNotFoundError as e:
        return str(e)
    except RuntimeError as e:
        return f"Slicing failed: {e}"

    return await upload_gcode(
        out_path,
        printer_uuid,
        team_id=team_id,
        auto_continue_dialogs=auto_continue_dialogs,
        tool_mapping=tool_mapping,
        start_print=start_print,
    )


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
