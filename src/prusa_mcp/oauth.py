"""OAuth2 Authorization Code + PKCE flow for Prusa Account.

Prusa Connect's internal REST API (``/app/*``) is authenticated via OAuth2
Bearer tokens issued by ``account.prusa3d.com`` — the same public client
that the official PrusaSlicer desktop app uses. This module implements:

- An interactive login via loopback redirect (PKCE, no client secret).
- Persistent storage of the refresh token on disk (0600 permissions).
- Silent refresh of expired access tokens.
- A single async accessor ``get_access_token()`` used by the MCP tools.

The token file path defaults to ``~/.config/prusa-mcp/tokens.json`` but can
be overridden with ``PRUSA_TOKEN_FILE`` — useful inside containers where the
file lives on a mounted volume shared with the host.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import http.server
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import threading
import time
from typing import Any
import urllib.parse
import webbrowser

import httpx

logger = logging.getLogger(__name__)


# ----------------------------
# Constants (public OAuth client)
# ----------------------------
ACCOUNT_URL = os.environ.get("PRUSA_ACCOUNT_URL", "https://account.prusa3d.com").rstrip("/")

# Public client id used by PrusaSlicer / Prusa Connect web app. Served from
# https://connect.prusa3d.com/environment.js as ACCOUNT_CLIENT_ID.
CLIENT_ID = os.environ.get("PRUSA_OAUTH_CLIENT_ID", "MRHTlZhZqkNrrQ6FUPtjyusAz8nc59ErHXP8XkS4")

TOKEN_URL = f"{ACCOUNT_URL}/o/token/"
AUTHORIZE_URL = f"{ACCOUNT_URL}/o/authorize/"

# Scopes observed on the Connect web app access token.
SCOPES = "basic_info connect user_operations email_lists openid"

# Refresh a little before real expiry to avoid races.
EXPIRY_LEEWAY_SECONDS = 60


# ----------------------------
# Errors
# ----------------------------
class LoginRequired(RuntimeError):  # noqa: N818
    """Raised when no usable token is available and interactive login is required."""


# ----------------------------
# Token storage
# ----------------------------
def _default_token_path() -> Path:
    """Return the token file path, honoring ``PRUSA_TOKEN_FILE``."""
    env = os.environ.get("PRUSA_TOKEN_FILE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / "prusa-mcp" / "tokens.json"


def _load_tokens() -> dict[str, Any] | None:
    """Load tokens from disk, returning ``None`` when the file is missing or unreadable."""
    path = _default_token_path()
    if not path.exists():
        return None
    try:
        with path.open() as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read token file at %s", path)
        return None
    return data


def _save_tokens(tokens: dict[str, Any]) -> None:
    """Persist tokens to disk with 0600 permissions."""
    path = _default_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(tokens, f, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        # chmod may fail on some filesystems (e.g. bound-mounts on Windows hosts);
        # the rename below still succeeds and the data is written.
        logger.debug("chmod 0600 failed for %s", tmp)
    tmp.replace(path)


# ----------------------------
# JWT expiry
# ----------------------------
def _jwt_exp(token: str) -> float | None:
    """Return the ``exp`` claim of a JWT, or ``None`` if it can't be parsed."""
    try:
        parts = token.split(".")
        if len(parts) < 2:  # noqa: PLR2004
            return None
        payload_b64 = parts[1]
        # Re-pad for urlsafe_b64decode
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        exp = payload.get("exp")
        return float(exp) if exp is not None else None
    except (ValueError, json.JSONDecodeError, TypeError):
        return None


def _is_expired(token: str, *, leeway: int = EXPIRY_LEEWAY_SECONDS) -> bool:
    """True if the token is expired or within ``leeway`` seconds of expiring."""
    exp = _jwt_exp(token)
    if exp is None:
        # If we can't read the exp, assume expired and force a refresh.
        return True
    return time.time() + leeway >= exp


# ----------------------------
# PKCE
# ----------------------------
def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE ``(verifier, challenge)`` pair (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ----------------------------
# Loopback callback server
# ----------------------------
class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Single-shot handler that captures the ``code`` query parameter."""

    # These are set by the outer login function on the class.
    result: dict[str, str] = {}  # noqa: RUF012
    done_event: threading.Event | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            _CallbackHandler.result["error"] = error
            body = f"<h1>Login failed</h1><p>{error}</p>".encode()
        elif code:
            _CallbackHandler.result["code"] = code
            if state:
                _CallbackHandler.result["state"] = state
            body = b"<h1>prusa-mcp: login successful</h1><p>You can close this tab and return to the terminal.</p>"
        else:
            _CallbackHandler.result["error"] = "missing_code"
            body = b"<h1>Login failed</h1><p>No authorization code received.</p>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

        if _CallbackHandler.done_event is not None:
            _CallbackHandler.done_event.set()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002
        # Silence default stderr logging from BaseHTTPRequestHandler.
        return


def _pick_free_port() -> int:
    """Ask the OS for a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ----------------------------
# Interactive login
# ----------------------------
def login_interactive(*, open_browser: bool = True, timeout: float = 300.0) -> dict[str, Any]:
    """Run the full PKCE flow, persist tokens, and return them.

    Args:
        open_browser: Automatically open the authorization URL in the user's
            default browser. When False, the URL is only printed — useful for
            headless or CI environments where you want to copy-paste manually.
        timeout: Seconds to wait for the callback before aborting.

    Raises:
        RuntimeError: on any failure (timeout, auth error, token exchange error).
    """
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    port = _pick_free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    auth_params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    authorize_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(auth_params)}"

    # Reset class-level state on the handler, then start the server.
    _CallbackHandler.result = {}
    _CallbackHandler.done_event = threading.Event()
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        print(f"\nOpen this URL in your browser to log in to Prusa Account:\n\n  {authorize_url}\n")
        if open_browser:
            try:
                webbrowser.open(authorize_url)
            except webbrowser.Error:
                logger.debug("webbrowser.open failed; user will copy-paste manually")

        if not _CallbackHandler.done_event.wait(timeout=timeout):
            raise RuntimeError(f"Timed out after {timeout:.0f}s waiting for the OAuth callback.")
    finally:
        server.shutdown()
        server.server_close()

    result = _CallbackHandler.result
    if "error" in result:
        raise RuntimeError(f"OAuth authorization failed: {result['error']}")
    if result.get("state") != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF, aborting.")
    code = result.get("code")
    if not code:
        raise RuntimeError("OAuth authorization did not return a code.")

    # Exchange the code for tokens.
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": CLIENT_ID,
        "code_verifier": verifier,
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(TOKEN_URL, data=token_payload)
    if resp.status_code != 200:  # noqa: PLR2004
        raise RuntimeError(f"Token exchange failed: HTTP {resp.status_code} — {resp.text}")

    tokens = resp.json()
    _save_tokens(tokens)
    logger.info("Saved Prusa tokens to %s", _default_token_path())
    return tokens


# ----------------------------
# Refresh
# ----------------------------
async def _refresh(refresh_token: str) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(TOKEN_URL, data=payload)
    if resp.status_code != 200:  # noqa: PLR2004
        raise LoginRequired(
            f"Token refresh failed (HTTP {resp.status_code}): {resp.text.strip() or 'no body'}. "
            f"Run `prusa-mcp login` to re-authenticate."
        )
    new_tokens = resp.json()
    # Django OAuth Toolkit rotates refresh tokens on each use and also returns
    # a new one in the response. Persist whatever we got back.
    _save_tokens(new_tokens)
    return new_tokens


# ----------------------------
# Public accessor
# ----------------------------
_lock = asyncio.Lock()
_cached: dict[str, Any] | None = None


async def get_access_token() -> str:
    """Return a valid access token, refreshing from disk when needed.

    Raises:
        LoginRequired: if no tokens are stored or the refresh token is rejected.
    """
    global _cached  # noqa: PLW0603

    async with _lock:
        if _cached is None:
            _cached = _load_tokens()
        if _cached is None:
            raise LoginRequired(
                "No Prusa tokens found. Run `prusa-mcp login` (or `uv run prusa-mcp login`) "
                "once to authenticate — this opens a browser window."
            )

        access = _cached.get("access_token")
        if access and not _is_expired(access):
            return access

        refresh_token = _cached.get("refresh_token")
        if not refresh_token:
            raise LoginRequired("Stored tokens are missing a refresh_token. Run `prusa-mcp login` again.")

        logger.debug("Access token expired or missing; refreshing.")
        _cached = await _refresh(refresh_token)
        access = _cached.get("access_token")
        if not access:
            raise LoginRequired("Refresh succeeded but no access_token was returned.")
        return access


def clear_cache() -> None:
    """Drop the in-memory token cache (forces the next call to re-read disk)."""
    global _cached  # noqa: PLW0603
    _cached = None
