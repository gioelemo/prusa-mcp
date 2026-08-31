# prusa-mcp

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

MCP server for interacting with Prusa Connect via OAuth2 (Authorization Code + PKCE) against Prusa Account — using the same public OAuth client id that the PrusaSlicer desktop app ships with.

## Features

- **OAuth2 Authentication**: One-time interactive login via an embedded native webview; refresh tokens are persisted and rotated automatically
- **Printer Management**: List all printers and get detailed status information
- **Job Tracking**: View recent print jobs for specific printers
- **File & Storage Management**: Browse printer files and storage devices
- **Printer Commands**: Send commands directly to printers (pause, resume, temperature, etc.) — see the full [command reference](supported_command.md)
- **Event Monitoring**: Fetch recent printer events
- **Multi-tool Support**: Inspect each tool's loaded filament and nozzle on machines like the XL, and slice for a specific tool
- **Slice & Print**: Slice an STL locally with the PrusaSlicer CLI, then upload and (optionally) print it via the Connect cloud — so the whole pipeline works even on restricted networks where only `connect.prusa3d.com` is reachable and local PrusaLink is blocked

## Installation

Install dependencies with uv:
```bash
uv sync
```

That's it on macOS and Windows. On Linux, `pywebview` additionally needs the system WebKit2GTK libraries for the login window — on Debian/Ubuntu that's `apt install gir1.2-webkit2-4.1 libgirepository1.0-dev`. (The MCP server itself never opens a window, so this is only needed on the host where you run `prusa-mcp login`.)

This server targets **MCP Python SDK v2** (`mcp>=2.0.0`), which speaks the current protocol revision. If you are upgrading from an older checkout, re-run `uv sync` — v2 replaces `httpx` with `httpx2` and drops the `mcp.server.fastmcp` module, so a stale environment will fail to import.

## Authentication

Run this once, on a machine with a display:

```bash
uv run prusa-mcp login
```

This opens a small native window showing the Prusa Account login page. You sign in with your Prusa credentials (SSO, 2FA, passkeys — whatever you use on the website); the moment Prusa Account finishes authorizing the client, the window closes automatically and access + refresh tokens are written to `~/.config/prusa-mcp/tokens.json` (override with `PRUSA_TOKEN_FILE`) with mode `0600`.

Under the hood: Prusa Account completes the flow by redirecting to `prusaslicer://login?code=...` — the custom URL scheme that the real PrusaSlicer desktop app registers with the OS. The embedded webview intercepts that navigation *before* the OS gets a chance to hand it off, so you never see PrusaSlicer pop up (even if you have it installed) and no paste-back is needed.

From then on the MCP server refreshes access tokens silently. You only need to re-run `prusa-mcp login` if the refresh token is ever revoked.

Running inside Docker? Run `prusa-mcp login` on the **host**, point `PRUSA_TOKEN_FILE` at a file on a volume mounted into the container, and the server will read and refresh tokens from there.

## Configuration

All environment variables are optional:

| Variable | Default | Description |
|----------|---------|-------------|
| `PRUSA_CONNECT_URL` | `https://connect.prusa3d.com` | Base URL for Prusa Connect |
| `PRUSA_ACCOUNT_URL` | `https://account.prusa3d.com` | Base URL for Prusa Account (OAuth) |
| `PRUSA_TOKEN_FILE` | `~/.config/prusa-mcp/tokens.json` | Path to the OAuth token file |
| `PRUSA_OAUTH_CLIENT_ID` | *(PrusaSlicer client)* | Override the public OAuth client id |
| `PRUSA_TEAM_ID` | *(auto-discovered)* | Connect team id used for uploads. Read it from the Connect upload URL `/app/users/teams/<id>/uploads`; if unset, it is looked up from the printer detail |
| `PRUSASLICER_CLI` | `prusa-slicer` | PrusaSlicer binary used for local slicing (macOS: `/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer`) |

Set these in your shell environment before running the server (e.g. `export PRUSA_CONNECT_URL=...`).

## Usage

### Claude Desktop

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "prusa-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/prusa-mcp",
        "run",
        "prusa-mcp"
      ]
    }
  }
}
```

### CLI

```bash
# Run the MCP server directly
uv run prusa-mcp

# Or via python module
python -m prusa_mcp
```

### Example script

[`examples/print_stl.py`](examples/print_stl.py) drives the whole pipeline from the command line, without an MCP client:

```bash
uv run examples/print_stl.py --list                                    # show printers
uv run examples/print_stl.py cube.stl --config lab_xl.ini              # slice, upload, print
uv run examples/print_stl.py cube.bgcode --printer "Printer 1" --no-print   # upload only
```

It prompts before starting a print; pass `--yes` to skip that. `--auto-continue` additionally dismisses the printer's "unfinished selftest" warning (see `auto_continue_dialogs` below).

### Available Tools

#### `connect_login`
Report the current Prusa Connect authentication status. Authentication itself happens out-of-band via the `prusa-mcp login` CLI subcommand (OAuth2 PKCE). This tool only checks that stored tokens are valid and refreshable. The legacy `email`/`password` parameters are accepted for backwards compatibility but ignored.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `email` | string | No | Ignored — kept for backwards compatibility |
| `password` | string | No | Ignored — kept for backwards compatibility |

#### `get_printers`
Get a list of all your Prusa printers.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Max printers to return (default: 10) |

#### `get_printer_status`
Get detailed status of a specific printer.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID or name of the printer |

#### `get_printer_jobs`
Get recent jobs for a specific printer.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID of the printer |
| `limit` | int | No | Max jobs to return (default: 5) |

#### `get_printer_files`
Get list of files on a printer.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID of the printer |
| `limit` | int | No | Max files to return (default: 100) |

#### `get_printer_storages`
Get storage devices for a printer.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID of the printer |

#### `delete_printer_file`
Delete a file from a printer's storage. **This cannot be undone.** Accepts either the printer's own path (`/usb/CUBE20~1.BGC`) or the display name (`cube20.bgcode`), resolving the latter against the file list. A name matching more than one file is refused with the candidates listed, rather than guessed at.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID of the printer |
| `path` | string | Yes | Printer path or display name of the file to delete |

#### `get_printer_tools`
List a printer's tools (extruders): loaded material, nozzle diameter, temperature, and which tool is active. On multi-tool machines like the XL each tool carries a different filament, so this is what tells you which tool to print a given material with. Unloaded tools show as `empty`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID of the printer |

#### `send_printer_command`
Send a command to a specific printer (e.g., pause, resume, set temperature).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID of the printer |
| `command` | string | Yes | Command name (see [command reference](supported_command.md)) |
| `args` | object | No | Command arguments |

#### `get_printer_events`
Fetch recent events for a printer.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `printer_uuid` | string | Yes | UUID of the printer |
| `limit` | int | No | Max events to return (default: 100) |

### Slice & Print Tools

These take an STL all the way to a running print over the Connect cloud. Slicing is local (needs a PrusaSlicer install — see `PRUSASLICER_CLI`); upload and print use the cloud API, so they work where local PrusaLink is blocked.

#### `slice_stl`
Slice a local STL into g-code/bgcode with the PrusaSlicer CLI. Runs entirely on the host — no network.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `stl_path` | string | Yes | Path to the input `.stl` |
| `config_ini` | string | Yes | Exported PrusaSlicer config bundle (File → Export → Export Config) |
| `output_path` | string | No | Output file (default: STL name with a `.bgcode` extension) |

#### `upload_gcode`
Upload a sliced g-code/bgcode file to a printer via the Connect cloud, optionally starting the print.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Local path to the `.bgcode`/`.gcode` file |
| `printer_uuid` | string | Yes | Target printer UUID |
| `team_id` | string | No | Connect team id (defaults to `PRUSA_TEAM_ID` or auto-discovery) |
| `auto_continue_dialogs` | list[str] | No | Dialog keys to confirm automatically, e.g. `["UNFINISHED_SELFTEST"]` (default: none) |
| `tool_mapping` | object | No | Remap g-code tools onto physical tools, e.g. `{"1": [3]}` (see below) |
| `start_print` | bool | No | If true, `START_PRINT` the uploaded file (default: false) |

After upload the tool waits for the file to appear on the printer, then starts it using the printer's own path — the printer's storage is FAT-formatted, so `cube.bgcode` becomes something like `/usb/CUBE20~1.BGC`, and re-uploading the same name yields `~2`, so the short name cannot be guessed.

`auto_continue_dialogs` confirms **only** the dialog keys you name. It deliberately offers no "accept anything" mode: the same channel carries filament-runout, thermal-anomaly and crash-detected dialogs, where auto-confirming would turn a stopped printer into a damaged one. Any dialog outside your list is reported and left for a human.

#### `slice_and_print`
One-shot: slice an STL, upload it, and (by default) start the print.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `stl_path` | string | Yes | Path to the input `.stl` |
| `printer_uuid` | string | Yes | Target printer UUID |
| `config_ini` | string | Yes | Exported PrusaSlicer config bundle |
| `team_id` | string | No | Connect team id (defaults to `PRUSA_TEAM_ID` or auto-discovery) |
| `auto_continue_dialogs` | list[str] | No | Dialog keys to confirm automatically (see `upload_gcode`) |
| `tool_mapping` | object | No | Remap g-code tools onto physical tools, e.g. `{"1": [3]}` (see below) |
| `start_print` | bool | No | Start the print after upload (default: true) |

### Printing with a specific tool (multi-tool printers)

On a multi-tool machine like the XL, each tool holds a different filament, so "pick an extruder" really means "pick the tool loaded with the material you want". Start by seeing what's loaded:

```bash
uv run python -c "
import asyncio, logging
logging.disable(logging.INFO)   # hide per-request HTTP logging
from prusa_mcp import server
print(asyncio.run(server.get_printer_tools('YOUR-PRINTER-UUID')))
"
```

```
Tool 1: PLA - nozzle 0.4mm - 26.0°C [ACTIVE]
Tool 2: PVB - nozzle 0.4mm - 28.0°C
Tool 3: PLA - nozzle 0.4mm - 28.0°C
Tool 4: FLEX - nozzle 0.4mm - 27.0°C
Tool 5: PETG - nozzle 0.4mm - 28.0°C
```

Which tool a print uses is **baked into the g-code at slicing time**, so select it with PrusaSlicer's `--extruder` (1-based), then upload the result:

```bash
# Slice for tool 3
/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer \
    --load config.ini --extruder 3 --export-gcode \
    --output cube_tool3.bgcode cube.stl

# Upload and print it
uv run examples/print_stl.py cube_tool3.bgcode --printer "Printer 1"
```

Verify the result before sending it: `--extruder 3` should produce `T2` tool-change commands (g-code numbers tools from 0) and `perimeter_extruder = 3` in the config footer. To read a `.bgcode`, re-slice with `--binary-gcode=0` for ASCII output — note the `=`, since `--binary-gcode 0` parses `0` as an input filename.

**Match the filament to the tool.** A bundle configured for PLA sliced onto a PETG tool prints at PLA temperatures on the wrong material. Either target a tool holding the same filament, or override it as well:

```bash
... --material-profile "Prusament PETG" --extruder 5 ...
```

#### Remapping at print time

`upload_gcode` and `slice_and_print` also take `tool_mapping`, which retargets a file without re-slicing it. Keys are the tools the **g-code** asks for, values are the **physical** tools to use, and both sides are 1-based:

```jsonc
{"1": [3]}          // g-code written for tool 1 → print it with tool 3
{"1": [3], "2": [5]} // a two-tool file remapped onto tools 3 and 5
```

Extra entries in a list are spool-join fallbacks (`{"1": [3, 4]}` continues on tool 4 when 3 runs out).

Two caveats. The printer **replaces** its entire mapping rather than merging, so map every tool the file uses — a tool you leave out is left unassigned, not left alone. And Connect validates the file path *before* the mapping, so a malformed mapping isn't reported by the API; it surfaces on the printer.

This shape is not in Prusa's public API docs. It was read off the firmware: [`command.cpp`](https://github.com/prusa3d/Prusa-Firmware-Buddy/blob/master/src/connect/command.cpp) parses `tool_mapping` as an object of numeric keys to arrays and converts both with `-1` ("internally tools are numbered from 0, externally from 1"), and [`marlin_printer.cpp`](https://github.com/prusa3d/Prusa-Firmware-Buddy/blob/master/src/connect/marlin_printer.cpp) applies it as `set_mapping(gcode_tool, virtual_tool)`.

## Security Notes

- **Token File**: The refresh and access tokens are stored in `PRUSA_TOKEN_FILE` (default `~/.config/prusa-mcp/tokens.json`), written with `0600` permissions. Treat this file like a password — anyone with a copy can act as you against Prusa Connect until the refresh token is revoked.
- **No Credentials on Disk**: Your Prusa Account email and password are never stored by this server; they are only ever entered on `account.prusa3d.com` itself during the one-time webview login.
- **Public Client + PKCE**: Authentication uses the public PrusaSlicer OAuth client with PKCE — there is no client secret to leak. The authorization code is bound to a per-login verifier, so intercepting the code alone is not enough to mint a token.
- **Dedicated Account**: Consider using a dedicated service account for automated access rather than your personal one.
- **Revoking Access**: To revoke this server's access, sign in to `account.prusa3d.com`, remove the authorized application, and delete the local token file.

## How It Works

1. **First Login**: Run `prusa-mcp login`. The CLI generates a PKCE pair and opens `account.prusa3d.com/o/authorize/` inside an embedded native webview (via `pywebview`). After you sign in, Prusa Account redirects the webview to `prusaslicer://login?code=...&state=...`. A background watcher thread polls the webview's current URL, captures the callback before the OS tries to dispatch the custom scheme, and destroys the window.
2. **Token Exchange**: The CLI posts the code + PKCE verifier to `account.prusa3d.com/o/token/` and receives an access token and a refresh token, which it writes to the token file.
3. **API Requests**: The MCP tools call `get_access_token()` before every request. If the cached access token is still valid (JWT `exp` check with a 60-second leeway), it's reused; otherwise the refresh token is exchanged for a new pair, which is written back to disk.
4. **Bearer Auth**: All Prusa Connect API calls attach `Authorization: Bearer <jwt>` — the same mechanism PrusaSlicer uses. This makes write endpoints like `send_printer_command` work, which cookie-based auth alone does not.

## Troubleshooting

- **`Not authenticated` from the tools**: Run `uv run prusa-mcp login` to generate or refresh the token file.
- **Refresh token rejected**: The refresh token may have been revoked (e.g. you changed your password or removed the authorized app in the Prusa Account dashboard). Delete the token file and run `prusa-mcp login` again.
- **Headless machines (no display)**: `prusa-mcp login` needs a windowed session to show the webview. Run the login on a desktop host (macOS, Windows, or Linux with X11/Wayland) and ship the resulting `tokens.json` to the headless machine via a mounted volume or `scp`.
- **Linux: `ImportError` about `gi` / `webkit2`**: Install the system WebKit2GTK bindings: `apt install gir1.2-webkit2-4.1 libgirepository1.0-dev` (Debian/Ubuntu) or the equivalent for your distribution.
- **Docker**: Run `prusa-mcp login` on the host, not inside the container. Point `PRUSA_TOKEN_FILE` at a path inside a volume mounted into both host and container.
- **TLS / certificate errors behind a proxy**: `httpx2` validates against the OS trust store (via `truststore`) instead of the bundled `certifi` roots. Import your proxy's CA into the system trust store, or point `SSL_CERT_FILE` / `SSL_CERT_DIR` at it.

## Development

```bash
uv sync --extra dev      # install dev tools (ruff, mypy, pytest)
uv run pytest            # run the test suite
uv run ruff check .      # lint
uv run ruff format .     # format
```

The tests fake all network calls and use a tiny stub slicer, so they run offline with no Prusa credentials and never touch a real printer.
