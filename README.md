# prusa-mcp
Small Prusa MCP Server

## Overview
MCP server that provides tools to interact with Prusa Connect via username/password authentication using Playwright browser automation.

## Features
- **Session-based Authentication**: Log in once with username and password, session cookies are persisted for future use
- **Printer Management**: List all printers and get detailed status information
- **Job Tracking**: View recent print jobs for specific printers

## Installation

1. Install dependencies with uv:
```bash
uv pip install -e .
```

2. Install Playwright browsers:
```bash
uv run playwright install chromium
```

## Configuration

The server uses the following environment variables (optional):

- `PRUSA_CONNECT_URL`: Base URL for Prusa Connect (default: `https://connect.prusa3d.com`)
- `PRUSA_CONNECT_STATE`: Path to session state file (default: `connect_state.json`)
- `HEADLESS`: Run browser in headless mode (default: `1`, set to `0` to watch the browser)
- `PW_TRACING`: Enable Playwright tracing for debugging (default: `0`)
- `PW_NAV_TIMEOUT_MS`: Navigation timeout in milliseconds (default: `30000`)
- `PW_SEL_TIMEOUT_MS`: Selector timeout in milliseconds (default: `15000`)

You can create a `.env` file to set these variables.

## Usage
Settings for Claude Desktop to be placed in `claude_desktop_config.json`
```
{
  "mcpServers": {
    "prusa-mcp": {
      "command": "/Users/gioelemolinari/.local/bin/uv",
      "args": [
        "--directory",
        "/Users/gioelemolinari/Desktop/prusa-mcp",
        "run",
        "src/prusa-mcp.py"
      ]
    }
  }
}
```

### Available Tools

#### 1. `connect_login`
Log in to Prusa Connect and save session cookies for later use.

**Parameters:**
- `email` (string): Your Prusa Connect email/username
- `password` (string): Your Prusa Connect password

**Example:**
```python
connect_login(email="your-email@example.com", password="your-password")
```

#### 2. `get_printers`
Get a list of all your Prusa printers.

**Parameters:**
- `limit` (int, optional): Maximum number of printers to return (default: 10)

**Example:**
```python
get_printers(limit=5)
```

#### 3. `get_printer_status`
Get detailed status of a specific printer.

**Parameters:**
- `printer_uuid` (string): The UUID or name of the printer

**Example:**
```python
get_printer_status(printer_uuid="your-printer-uuid")
```

#### 4. `get_printer_jobs`
Get recent jobs for a specific printer.

**Parameters:**
- `printer_uuid` (string): The UUID of the printer
- `limit` (int, optional): Maximum number of jobs to return (default: 5)

**Example:**
```python
get_printer_jobs(printer_uuid="your-printer-uuid", limit=10)
```

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
