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
    captured: dict = {}

    async def fake_cmd(printer_uuid, command, args=None):
        captured.update(printer_uuid=printer_uuid, command=command, args=args)
        return "Command 'START_PRINT' sent successfully"

    monkeypatch.setattr(server, "send_printer_command", fake_cmd)

    msg = await server.upload_gcode(str(bgcode_file), "uuid-2", team_id="t1", start_print=True)

    assert captured == {"printer_uuid": "uuid-2", "command": "START_PRINT", "args": {"path": "/usb/model.bgcode"}}
    assert "Command 'START_PRINT' sent successfully" in msg


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

    msg = await server.slice_and_print(str(stl), "uuid-9", str(cfg), team_id="t2")

    # Sliced output got uploaded...
    assert rec["post"]["json"]["filename"] == "s.bgcode"
    assert rec["post"]["json"]["size"] == len(b"GCODE")
    # ...and START_PRINT fired with the path from the register response.
    assert captured["command"] == "START_PRINT"
    assert captured["args"] == {"path": "/usb/model.bgcode"}
    assert "started" in msg
