"""Tests for the slice / upload / print tools added for Prusa Connect cloud.

Network calls are faked (no real Connect traffic, no auth, no physical print);
slicing is exercised with a tiny fake CLI that just writes the --output file.
"""

from typing import Self

import httpx2
import pytest

from prusa_mcp import server


# ----------------------------
# Helpers / fixtures
# ----------------------------
async def _fake_auth_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Stand-in for server._auth_headers that needs no token on disk."""
    headers = {"Authorization": "Bearer test", "Accept": "application/json"}
    if extra:
        headers.update(extra)
    return headers


def _resp(method: str, url: str, status: int, data: dict) -> httpx2.Response:
    return httpx2.Response(status, json=data, request=httpx2.Request(method, url))


# The printer's USB is FAT-formatted, so Connect reports both the long display
# name and the 8.3 short path that START_PRINT actually resolves.
_PRINTER_FILE = {
    "name": "model.bgcode",
    "display_name": "model.bgcode",
    "path": "/usb/MODEL~1.BGC",
    "display_path": "/usb/model.bgcode",
}

_DIALOG = {
    "id": 42,
    "code": "17801",
    "key": "UNFINISHED_SELFTEST",
    "title": "Warning",
    "text": "Please complete Calibrations & Tests before using the printer.",
    "buttons": ["Continue", "Abort"],
}


async def _fake_files_listing(endpoint: str) -> dict:
    """Stand-in for make_prusa_request returning one file on the printer."""
    return {"files": [_PRINTER_FILE]}


def _patch_httpx(monkeypatch, *, post_status: int = 200, post_json: dict | None = None) -> dict:
    """Patch ``server.httpx2.AsyncClient`` with a fake; return a record of the calls."""
    rec: dict = {}
    body = post_json if post_json is not None else {"id": 4242, "path": "/usb/model.bgcode", "state": "INITIATED"}

    class Client:
        def __init__(self, *args, **kwargs) -> None: ...
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args) -> bool:
            return False

        async def post(self, url, *, headers=None, json=None):
            rec["post"] = {"url": url, "headers": headers, "json": json}
            return _resp("POST", url, post_status, body)

        async def put(self, url, *, params=None, headers=None, content=None):
            rec["put"] = {
                "url": url,
                "params": params,
                "headers": headers,
                "content_len": len(content) if content else 0,
            }
            return _resp("PUT", url, 200, {})

    monkeypatch.setattr(server.httpx2, "AsyncClient", Client)
    return rec


@pytest.fixture
def bgcode_file(tmp_path):
    f = tmp_path / "model.bgcode"
    f.write_bytes(b"X" * 2048)
    return f


@pytest.fixture
def fake_slicer(tmp_path, monkeypatch):
    """A fake PrusaSlicer CLI that writes the requested --output file."""
    stl = tmp_path / "s.stl"
    stl.write_text("solid")
    cfg = tmp_path / "c.ini"
    cfg.write_text("cfg")
    script = tmp_path / "fakeslicer.sh"
    script.write_text(
        "#!/bin/sh\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--output" ]; then shift; OUT="$1"; fi\n'
        "  shift\n"
        "done\n"
        'printf GCODE > "$OUT"\n'
    )
    script.chmod(0o755)
    monkeypatch.setattr(server, "PRUSASLICER_CLI", str(script))
    return stl, cfg


# ----------------------------
# _read_file
# ----------------------------
def test_read_file_missing():
    with pytest.raises(FileNotFoundError):
        server._read_file("/no/such/file.bgcode")


def test_read_file_ok(tmp_path):
    f = tmp_path / "a.bgcode"
    f.write_bytes(b"hello")
    name, size, data = server._read_file(str(f))
    assert name == "a.bgcode"
    assert size == 5
    assert data == b"hello"


# ----------------------------
# _slice_to_gcode
# ----------------------------
def test_slice_missing_stl(tmp_path):
    cfg = tmp_path / "c.ini"
    cfg.write_text("x")
    with pytest.raises(FileNotFoundError):
        server._slice_to_gcode("/no/such.stl", str(cfg))


def test_slice_missing_cfg(tmp_path):
    stl = tmp_path / "s.stl"
    stl.write_text("x")
    with pytest.raises(FileNotFoundError):
        server._slice_to_gcode(str(stl), "/no/such.ini")


def test_slice_cli_not_found(tmp_path, monkeypatch):
    stl = tmp_path / "s.stl"
    stl.write_text("x")
    cfg = tmp_path / "c.ini"
    cfg.write_text("x")
    monkeypatch.setattr(server, "PRUSASLICER_CLI", "definitely-not-a-real-binary-xyz")
    with pytest.raises(RuntimeError, match="not found"):
        server._slice_to_gcode(str(stl), str(cfg))


def test_slice_success(fake_slicer):
    stl, cfg = fake_slicer
    out_path, size, name = server._slice_to_gcode(str(stl), str(cfg))
    assert name == "s.stl"
    assert out_path == str(stl.with_suffix(".bgcode"))
    assert size == len(b"GCODE")


# ----------------------------
# _resolve_team_id
# ----------------------------
async def test_resolve_team_id_arg_wins():
    assert await server._resolve_team_id("uuid", "explicit") == "explicit"


async def test_resolve_team_id_env(monkeypatch):
    monkeypatch.setattr(server, "DEFAULT_TEAM_ID", "envteam")
    assert await server._resolve_team_id("uuid", "") == "envteam"


async def test_resolve_team_id_discovered(monkeypatch):
    monkeypatch.setattr(server, "DEFAULT_TEAM_ID", "")

    async def fake_req(endpoint):
        assert endpoint == "/printers/uuid"
        return {"team_id": "discovered"}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert await server._resolve_team_id("uuid", "") == "discovered"


async def test_resolve_team_id_none(monkeypatch):
    monkeypatch.setattr(server, "DEFAULT_TEAM_ID", "")

    async def fake_req(endpoint):
        return None

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert await server._resolve_team_id("uuid", "") is None


# ----------------------------
# get_printer_jobs
# ----------------------------
# Shaped like a real Connect job: the filename is nested under "file", the
# timestamps are Unix epochs, and a finished job carries no "progress".
_JOB = {
    "id": 246,
    "state": "FIN_STOPPED",
    "path": "/usb/CUBE_T~1.BGC",
    "start": 1788185986,
    "end": 1788186031,
    "time_printing": 760,
    "file": {"name": "cube_tool3.bgcode", "display_name": "cube_tool3.bgcode"},
}


async def test_get_printer_jobs_formats_a_job(monkeypatch):
    async def fake_req(endpoint):
        assert endpoint == "/printers/uuid-1/jobs?limit=5"
        return {"jobs": [_JOB]}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    out = await server.get_printer_jobs("uuid-1")

    assert "File: cube_tool3.bgcode" in out  # not the 8.3 path, not "Unknown"
    assert "Status: FIN_STOPPED" in out
    assert "Started: 2026-08-31 14:19:46 UTC" in out  # not a raw epoch
    assert "Ended: 2026-08-31 14:20:31 UTC" in out  # "end", not "completed_at"
    # Duration comes from the timestamps (45s), NOT time_printing (760s), which
    # holds the previous job's value on a job that was stopped early.
    assert "Duration: 45s" in out
    assert "12m 40s" not in out
    # A finished job has no progress; don't render a meaningless "N/A%".
    assert "Progress" not in out


async def test_get_printer_jobs_shows_progress_only_when_present(monkeypatch):
    async def fake_req(endpoint):
        return {"jobs": [{**_JOB, "state": "PRINTING", "end": None, "progress": 35.0}]}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    out = await server.get_printer_jobs("uuid-1")

    assert "Progress: 35.0%" in out
    assert "Ended" not in out
    assert "Duration" not in out


async def test_get_printer_jobs_falls_back_to_path(monkeypatch):
    async def fake_req(endpoint):
        return {"jobs": [{"id": 1, "path": "/usb/ONLY~1.BGC"}]}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert "File: /usb/ONLY~1.BGC" in await server.get_printer_jobs("uuid-1")


async def test_get_printer_jobs_empty(monkeypatch):
    async def fake_req(endpoint):
        return {"jobs": []}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert "No jobs found" in await server.get_printer_jobs("uuid-1")


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0s"), (45, "45s"), (760, "12m 40s"), (9796, "2h 43m 16s"), (3600, "1h 0m 0s")],
)
def test_format_duration(seconds, expected):
    assert server._format_duration(seconds) == expected


@pytest.mark.parametrize("bad", [None, "", "not-a-number"])
def test_format_timestamp_and_duration_survive_junk(bad):
    assert server._format_timestamp(bad) == "Unknown"
    assert server._format_duration(bad) == "Unknown"


# ----------------------------
# delete_printer_file
# ----------------------------
_FILES = [
    {"display_name": "cube20.bgcode", "name": "cube20.bgcode", "path": "/usb/CUBE20~1.BGC"},
    {"display_name": "cube20[1].bgcode", "name": "cube20[1].bgcode", "path": "/usb/CUBE20~2.BGC"},
    {"display_name": "dup.bgcode", "name": "dup.bgcode", "path": "/usb/DUP~1.BGC"},
    {"display_name": "dup.bgcode", "name": "dup.bgcode", "path": "/usb/ARCHIVE/DUP~2.BGC"},
]


def _patch_files(monkeypatch, files=None):
    async def fake_req(endpoint):
        assert "/files" in endpoint
        return {"files": _FILES if files is None else files}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)


def _capture_commands(monkeypatch) -> dict:
    captured: dict = {}

    async def fake_cmd(printer_uuid, command, args=None):
        captured.update(printer_uuid=printer_uuid, command=command, args=args)
        return "ok"

    monkeypatch.setattr(server, "send_printer_command", fake_cmd)
    return captured


async def test_delete_printer_file_by_display_name(monkeypatch):
    _patch_files(monkeypatch)
    captured = _capture_commands(monkeypatch)

    out = await server.delete_printer_file("uuid-1", "cube20.bgcode")

    # Resolved to the printer's 8.3 path, not the name we were given.
    assert captured == {
        "printer_uuid": "uuid-1",
        "command": "DELETE_FILE",
        "args": {"path": "/usb/CUBE20~1.BGC"},
    }
    assert "/usb/CUBE20~1.BGC" in out


async def test_delete_printer_file_by_exact_path(monkeypatch):
    _patch_files(monkeypatch)
    captured = _capture_commands(monkeypatch)

    await server.delete_printer_file("uuid-1", "/usb/CUBE20~2.BGC")
    assert captured["args"] == {"path": "/usb/CUBE20~2.BGC"}


async def test_delete_printer_file_refuses_ambiguous_name(monkeypatch):
    """Never guess between two files sharing a name -- deletion is irreversible."""
    _patch_files(monkeypatch)

    async def boom(*args, **kwargs):
        raise AssertionError("must not delete on an ambiguous match")

    monkeypatch.setattr(server, "send_printer_command", boom)

    out = await server.delete_printer_file("uuid-1", "dup.bgcode")

    assert "matches 2 files" in out
    assert "/usb/DUP~1.BGC" in out
    assert "/usb/ARCHIVE/DUP~2.BGC" in out


async def test_delete_printer_file_not_found(monkeypatch):
    _patch_files(monkeypatch)

    async def boom(*args, **kwargs):
        raise AssertionError("must not send a command when nothing matched")

    monkeypatch.setattr(server, "send_printer_command", boom)
    assert "No file matching" in await server.delete_printer_file("uuid-1", "nope.bgcode")


async def test_delete_printer_file_request_failed(monkeypatch):
    async def fake_req(endpoint):
        return None

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert "Unable to fetch files" in await server.delete_printer_file("uuid-1", "cube20.bgcode")


# ----------------------------
# get_printer_tools
# ----------------------------
# Shaped like a real Prusa XL: five tools, a different filament in each.
_TOOLS = {
    "1": {"material": "PLA", "nozzle_diameter": 0.4, "temp": 69.0, "active": True},
    "2": {"material": "PVB", "nozzle_diameter": 0.4, "temp": 27.0},
    "5": {"material": "PETG", "nozzle_diameter": 0.6, "temp": 28.0, "hardened": True, "high_flow": True},
}


async def test_get_printer_tools_lists_each_tool(monkeypatch):
    async def fake_req(endpoint):
        assert endpoint == "/printers/uuid-1"
        return {"tools": _TOOLS}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)

    out = await server.get_printer_tools("uuid-1")
    lines = out.splitlines()

    # Connect keys tools as strings, so they must be ordered numerically.
    assert [line.split(":")[0] for line in lines] == ["Tool 1", "Tool 2", "Tool 5"]
    assert "PLA - nozzle 0.4mm - 69.0°C [ACTIVE]" in lines[0]
    assert lines[1].endswith("27.0°C")  # no flags -> no bracket
    assert "[hardened, high-flow]" in lines[2]


@pytest.mark.parametrize("material", [None, "", "---"])
async def test_get_printer_tools_reports_empty_slot(monkeypatch, material):
    """An unloaded tool reads as "---" on a real XL, not as null."""

    async def fake_req(endpoint):
        return {"tools": {"1": {"material": material, "nozzle_diameter": 0.4, "temp": 25.0}}}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert "Tool 1: empty" in await server.get_printer_tools("uuid-1")


async def test_get_printer_tools_single_tool_printer(monkeypatch):
    async def fake_req(endpoint):
        return {"printer_state": "IDLE"}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert "no per-tool information" in await server.get_printer_tools("uuid-1")


async def test_get_printer_tools_request_failed(monkeypatch):
    async def fake_req(endpoint):
        return None

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    assert "Unable to fetch tools" in await server.get_printer_tools("uuid-1")


# ----------------------------
# upload_gcode
# ----------------------------
async def test_upload_gcode_registers_and_puts(monkeypatch, bgcode_file):
    rec = _patch_httpx(monkeypatch)
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)

    msg = await server.upload_gcode(str(bgcode_file), "uuid-1", team_id="team-9")

    assert "Uploaded model.bgcode" in msg
    assert "/usb/model.bgcode" in msg
    assert rec["post"]["url"].endswith("/app/users/teams/team-9/uploads")
    assert rec["post"]["json"] == {"filename": "model.bgcode", "printer_uuid": "uuid-1", "size": 2048}
    assert rec["put"]["url"].endswith("/app/teams/team-9/files/raw")
    assert rec["put"]["params"] == {"upload_id": 4242}
    assert rec["put"]["content_len"] == 2048
    assert rec["put"]["headers"]["upload-size"] == "2048"
    assert rec["put"]["headers"]["Content-Type"] == "text/x.gcode"


async def test_upload_gcode_start_print(monkeypatch, bgcode_file):
    _patch_httpx(monkeypatch)
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)
    monkeypatch.setattr(server, "make_prusa_request", _fake_files_listing)
    captured: dict = {}

    async def fake_cmd(printer_uuid, command, args=None):
        captured.update(printer_uuid=printer_uuid, command=command, args=args)
        return "Command 'START_PRINT' sent successfully"

    monkeypatch.setattr(server, "send_printer_command", fake_cmd)

    msg = await server.upload_gcode(str(bgcode_file), "uuid-2", team_id="t1", start_print=True)

    # START_PRINT must use the printer's own 8.3 short path, not the long name
    # Connect echoes back from the upload registration.
    assert captured == {
        "printer_uuid": "uuid-2",
        "command": "START_PRINT",
        "args": {"path": "/usb/MODEL~1.BGC"},
    }
    assert "Command 'START_PRINT' sent successfully" in msg


async def test_upload_gcode_start_print_with_tool_mapping(monkeypatch, bgcode_file):
    """Keys are the g-code's tools, values the physical tools; both 1-based.

    Derived from Prusa-Firmware-Buddy: command.cpp parses tool_mapping as an
    object of numeric keys to arrays, converting both with -1 ("internally tools
    are numbered from 0, externally from 1"), and marlin_printer.cpp applies it
    as set_mapping(gcode_tool, virtual_tool).
    """
    _patch_httpx(monkeypatch)
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)
    monkeypatch.setattr(server, "make_prusa_request", _fake_files_listing)
    captured: dict = {}

    async def fake_cmd(printer_uuid, command, args=None):
        captured.update(command=command, args=args)
        return "started"

    monkeypatch.setattr(server, "send_printer_command", fake_cmd)

    await server.upload_gcode(str(bgcode_file), "uuid-2", team_id="t1", tool_mapping={"1": [3]}, start_print=True)

    assert captured["args"] == {"path": "/usb/MODEL~1.BGC", "tool_mapping": {"1": [3]}}


async def test_upload_gcode_omits_tool_mapping_when_unset(monkeypatch, bgcode_file):
    _patch_httpx(monkeypatch)
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)
    monkeypatch.setattr(server, "make_prusa_request", _fake_files_listing)
    captured: dict = {}

    async def fake_cmd(printer_uuid, command, args=None):
        captured.update(args=args)
        return "started"

    monkeypatch.setattr(server, "send_printer_command", fake_cmd)

    await server.upload_gcode(str(bgcode_file), "uuid-2", team_id="t1", start_print=True)
    assert captured["args"] == {"path": "/usb/MODEL~1.BGC"}


async def test_send_printer_command_sends_kwargs_not_args(monkeypatch):
    """Connect rejects ``args`` with MISSING_COMMAND_ARGUMENT; it requires ``kwargs``."""
    rec = _patch_httpx(monkeypatch)
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)

    await server.send_printer_command("uuid-1", "START_PRINT", {"path": "/usb/MODEL~1.BGC"})

    assert rec["post"]["json"] == {"command": "START_PRINT", "kwargs": {"path": "/usb/MODEL~1.BGC"}}
    assert "args" not in rec["post"]["json"]


async def test_send_printer_command_without_args_omits_kwargs(monkeypatch):
    rec = _patch_httpx(monkeypatch)
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)

    await server.send_printer_command("uuid-1", "PAUSE_PRINT")

    assert rec["post"]["json"] == {"command": "PAUSE_PRINT"}


# ----------------------------
# _wait_for_printer_file
# ----------------------------
async def test_wait_for_printer_file_returns_short_path(monkeypatch):
    monkeypatch.setattr(server, "make_prusa_request", _fake_files_listing)
    assert await server._wait_for_printer_file("uuid", "model.bgcode") == "/usb/MODEL~1.BGC"


async def test_wait_for_printer_file_times_out(monkeypatch):
    async def empty(endpoint):
        return {"files": []}

    monkeypatch.setattr(server, "make_prusa_request", empty)
    monkeypatch.setattr(server, "FILE_POLL_INTERVAL_SECONDS", 0)
    assert await server._wait_for_printer_file("uuid", "gone.bgcode", timeout_seconds=0.01) is None


# ----------------------------
# _auto_continue_dialog (targeted, opt-in)
# ----------------------------
async def test_auto_continue_dialog_confirms_allow_listed_key(monkeypatch):
    async def fake_req(endpoint):
        return {"dialog_info": _DIALOG}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    captured: dict = {}

    async def fake_cmd(printer_uuid, command, args=None):
        captured.update(command=command, args=args)
        return "ok"

    monkeypatch.setattr(server, "send_printer_command", fake_cmd)

    out = await server._auto_continue_dialog("uuid", {"UNFINISHED_SELFTEST"})

    assert captured == {"command": "DIALOG_ACTION", "args": {"dialog_id": 42, "button": "Continue"}}
    assert "Auto-confirmed" in out


async def test_auto_continue_dialog_leaves_unlisted_dialog_alone(monkeypatch):
    """A safety dialog must never be auto-confirmed just because auto-continue is on."""

    async def fake_req(endpoint):
        return {"dialog_info": {**_DIALOG, "key": "FILAMENT_RUNOUT"}}

    monkeypatch.setattr(server, "make_prusa_request", fake_req)

    async def boom(*args, **kwargs):
        raise AssertionError("must not confirm a dialog outside the allow-list")

    monkeypatch.setattr(server, "send_printer_command", boom)

    out = await server._auto_continue_dialog("uuid", {"UNFINISHED_SELFTEST"})

    assert "FILAMENT_RUNOUT" in out
    assert "leaving it for a human" in out


async def test_upload_gcode_http_error(monkeypatch, bgcode_file):
    _patch_httpx(monkeypatch, post_status=400, post_json={"message": "nope"})
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)

    msg = await server.upload_gcode(str(bgcode_file), "uuid-3", team_id="t1")
    assert "Upload failed: HTTP 400" in msg


async def test_upload_gcode_missing_file():
    msg = await server.upload_gcode("/no/such/file.bgcode", "uuid", team_id="t1")
    assert "File not found" in msg


async def test_upload_gcode_no_team_id(monkeypatch, bgcode_file):
    monkeypatch.setattr(server, "DEFAULT_TEAM_ID", "")

    async def fake_req(endpoint):
        return None

    monkeypatch.setattr(server, "make_prusa_request", fake_req)
    msg = await server.upload_gcode(str(bgcode_file), "uuid")
    assert "Could not determine team_id" in msg


# ----------------------------
# slice_stl tool
# ----------------------------
async def test_slice_stl_tool_success(fake_slicer):
    stl, cfg = fake_slicer
    msg = await server.slice_stl(str(stl), str(cfg))
    assert "Sliced s.stl ->" in msg
    assert "bytes" in msg


async def test_slice_stl_tool_missing_stl():
    msg = await server.slice_stl("/no/such.stl", "/no/such.ini")
    assert "STL not found" in msg


# ----------------------------
# slice_and_print (slice -> upload -> START_PRINT)
# ----------------------------
async def test_slice_and_print_chains(monkeypatch, fake_slicer):
    stl, cfg = fake_slicer
    rec = _patch_httpx(monkeypatch)
    monkeypatch.setattr(server, "_auth_headers", _fake_auth_headers)
    captured: dict = {}

    async def fake_cmd(printer_uuid, command, args=None):
        captured.update(printer_uuid=printer_uuid, command=command, args=args)
        return "started"

    monkeypatch.setattr(server, "send_printer_command", fake_cmd)

    async def fake_files(endpoint):
        return {"files": [{"display_name": "s.bgcode", "name": "s.bgcode", "path": "/usb/S~1.BGC"}]}

    monkeypatch.setattr(server, "make_prusa_request", fake_files)

    msg = await server.slice_and_print(str(stl), "uuid-9", str(cfg), team_id="t2")

    # Sliced output got uploaded...
    assert rec["post"]["json"]["filename"] == "s.bgcode"
    assert rec["post"]["json"]["size"] == len(b"GCODE")
    # ...and START_PRINT fired with the printer's own short path for it.
    assert captured["command"] == "START_PRINT"
    assert captured["args"] == {"path": "/usb/S~1.BGC"}
    assert "started" in msg
