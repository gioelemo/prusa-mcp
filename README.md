# prusa-mcp

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

MCP server for interacting with Prusa Connect via session-based authentication using Playwright browser automation.

## Features

- **Session-based Authentication**: Log in once with username and password, session cookies are persisted for future use
- **Printer Management**: List all printers and get detailed status information
- **Job Tracking**: View recent print jobs for specific printers
- **File & Storage Management**: Browse printer files and storage devices
- **Printer Commands**: Send commands directly to printers (pause, resume, temperature, etc.) — see the full [command reference](supported_command.md)
- **Event Monitoring**: Fetch recent printer events

## Installation

1. Install dependencies with uv:
```bash
uv sync
```

2. Install Playwright browsers:
```bash
uv run playwright install chromium
```

## Configuration

The server uses the following environment variables (optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `PRUSA_CONNECT_URL` | `https://connect.prusa3d.com` | Base URL for Prusa Connect |
| `PRUSA_CONNECT_STATE` | `connect_state.json` | Path to session state file |
| `PRUSA_EMAIL` | — | Default login email |
| `PRUSA_PASSWORD` | — | Default login password |
| `HEADLESS` | `1` | Run browser headless (`0` to watch) |
| `PW_TRACING` | `0` | Enable Playwright tracing |
| `PW_NAV_TIMEOUT_MS` | `30000` | Navigation timeout (ms) |
| `PW_SEL_TIMEOUT_MS` | `15000` | Selector timeout (ms) |

You can create a `.env` file to set these variables.

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

### Available Tools

#### `connect_login`
Log in to Prusa Connect and save session cookies for later use.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `email` | string | No | Prusa Connect email (falls back to `PRUSA_EMAIL`) |
| `password` | string | No | Prusa Connect password (falls back to `PRUSA_PASSWORD`) |

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

## Security Notes

- **Session Persistence**: The server stores session cookies in `connect_state.json` (or the path specified in `PRUSA_CONNECT_STATE`). This file contains your logged-in session and should be treated as sensitive.
- **Dedicated Account**: Consider using a dedicated service account for automated access rather than your personal account.
- **Credentials**: Never hard-code credentials in your scripts. Use the `connect_login` tool to authenticate at runtime or store credentials securely in environment variables.

## How It Works

1. **First Login**: Call `connect_login` with your username and password. The server uses Playwright to automate the browser login process.
2. **Session Storage**: After successful login, session cookies are saved to `connect_state.json`.
3. **Subsequent Requests**: All API calls use the stored session cookies, so you don't need to log in again until the session expires.
4. **API Access**: The server makes HTTP requests to the Prusa Connect API using the authenticated session.

## Troubleshooting

- **Login Issues**: If login fails, try setting `HEADLESS=0` to watch the browser and see what's happening.
- **Session Expired**: If you get authentication errors, delete `connect_state.json` and log in again.
- **Tracing**: Enable `PW_TRACING=1` to generate a trace file (`trace.zip`) for debugging Playwright issues.
