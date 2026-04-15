# prusa-mcp

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

MCP server for interacting with Prusa Connect via OAuth2 (Authorization Code + PKCE) against Prusa Account — the same public client used by PrusaSlicer and the Connect web app.

## Features

- **OAuth2 Authentication**: One-time interactive login via your browser; refresh tokens are persisted and rotated automatically
- **Printer Management**: List all printers and get detailed status information
- **Job Tracking**: View recent print jobs for specific printers
- **File & Storage Management**: Browse printer files and storage devices
- **Printer Commands**: Send commands directly to printers (pause, resume, temperature, etc.) — see the full [command reference](supported_command.md)
- **Event Monitoring**: Fetch recent printer events

## Installation

Install dependencies with uv:
```bash
uv sync
```

That's it — no browser binaries, no system packages.

## Authentication

Run this once, on a machine with a web browser:

```bash
uv run prusa-mcp login
```

This opens your default browser at `account.prusa3d.com`, you log in with your Prusa credentials (SSO, 2FA, passkeys — whatever you use on the website), and the server receives the OAuth callback on `127.0.0.1`. Access and refresh tokens are saved to `~/.config/prusa-mcp/tokens.json` (override with `PRUSA_TOKEN_FILE`) with mode `0600`.

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

You can create a `.env` file from `.env.example` to set these.

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

- **Token File**: The refresh and access tokens are stored in `PRUSA_TOKEN_FILE` (default `~/.config/prusa-mcp/tokens.json`), written with `0600` permissions. Treat this file like a password — anyone with a copy can act as you against Prusa Connect until the refresh token is revoked.
- **No Credentials on Disk**: Your Prusa Account email and password are never stored by this server; they are only ever entered on `account.prusa3d.com` itself during the one-time browser login.
- **Public Client + PKCE**: Authentication uses the public PrusaSlicer OAuth client with PKCE — there is no client secret to leak. The authorization code is bound to a per-login verifier and a loopback redirect on `127.0.0.1`, so intercepting the code is not enough to mint a token.
- **Dedicated Account**: Consider using a dedicated service account for automated access rather than your personal one.
- **Revoking Access**: To revoke this server's access, sign in to `account.prusa3d.com`, remove the authorized application, and delete the local token file.

## How It Works

1. **First Login**: Run `prusa-mcp login`. The CLI generates a PKCE pair, starts a loopback HTTP server on a random port, and opens `account.prusa3d.com/o/authorize/` in your browser. After you sign in, Prusa Account redirects to `http://127.0.0.1:<port>/callback` with an authorization code.
2. **Token Exchange**: The CLI posts the code + PKCE verifier to `account.prusa3d.com/o/token/` and receives an access token and a refresh token, which it writes to the token file.
3. **API Requests**: The MCP tools call `get_access_token()` before every request. If the cached access token is still valid (JWT `exp` check with a 60-second leeway), it's reused; otherwise the refresh token is exchanged for a new pair, which is written back to disk.
4. **Bearer Auth**: All Prusa Connect API calls attach `Authorization: Bearer <jwt>` — the same mechanism PrusaSlicer uses. This makes write endpoints like `send_printer_command` work, which cookie-based auth alone does not.

## Troubleshooting

- **`Not authenticated` from the tools**: Run `uv run prusa-mcp login` to generate or refresh the token file.
- **Refresh token rejected**: The refresh token may have been revoked (e.g. you changed your password or removed the authorized app in the Prusa Account dashboard). Delete the token file and run `prusa-mcp login` again.
- **Headless / no browser available**: Pass `--no-browser` to `prusa-mcp login` and copy-paste the printed URL into any browser that can reach `account.prusa3d.com` and `127.0.0.1:<port>` on the machine running the CLI. For remote/SSH setups, use SSH port-forwarding or run the login on the host and share the token file via a mounted volume.
- **Docker**: Run `prusa-mcp login` on the host, not inside the container. Point `PRUSA_TOKEN_FILE` at a path inside a volume mounted into both host and container.
