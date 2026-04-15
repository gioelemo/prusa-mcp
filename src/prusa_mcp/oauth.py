"""OAuth2 Authorization Code + PKCE flow for Prusa Account.

Prusa Connect's internal REST API (``/app/*``) is authenticated via OAuth2
Bearer tokens issued by ``account.prusa3d.com`` — the same public client
that the official PrusaSlicer desktop app uses. This module implements:

- An interactive login via an embedded native webview (PKCE, no client secret).
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
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any
import urllib.parse

import httpx

logger = logging.getLogger(__name__)


# ----------------------------
# Constants (public OAuth client)
# ----------------------------
ACCOUNT_URL = os.environ.get("PRUSA_ACCOUNT_URL", "https://account.prusa3d.com").rstrip("/")

# Public OAuth client used by the PrusaSlicer desktop app. This is the same
# client id hard-coded in
# https://github.com/prusa3d/PrusaSlicer/blob/main/src/slic3r/Utils/ServiceConfig.cpp
# (``m_account_client_id``). We reuse it because it is the only public Prusa
# client whose registered redirect URI we can intercept without paste-back
# or a real browser: PrusaSlicer registers ``prusaslicer://login`` as an OS
# URL handler, and we can catch that navigation inside an embedded webview.
#
# The Connect web client ("MRHTl...") only accepts
# ``https://connect.prusa3d.com/login/auth-callback`` as a redirect, which
# would force the user to copy-paste the callback URL back into the CLI.
CLIENT_ID = os.environ.get("PRUSA_OAUTH_CLIENT_ID", "oamhmhZez7opFosnwzElIgE2oGgI2iJORSkw587O")

TOKEN_URL = f"{ACCOUNT_URL}/o/token/"
AUTHORIZE_URL = f"{ACCOUNT_URL}/o/authorize/"

# Custom-scheme redirect URI registered for the PrusaSlicer OAuth client.
# We never actually launch ``prusaslicer://login`` — we intercept the
# navigation inside our embedded webview before the OS tries to hand it off.
REDIRECT_URI = "prusaslicer://login"

# Scope requested by PrusaSlicer itself. Confirmed sufficient for the Connect
# ``/app/printers/`` family of endpoints: PrusaSlicer hits those endpoints with
# a token obtained from this exact (client_id, scope) pair.
SCOPES = "basic_info"

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
# Interactive login (paste-back flow)
# ----------------------------
def _extract_code_from_url(url: str) -> tuple[str, str | None]:
    """Parse a pasted callback URL and return ``(code, state)``.

    Accepts either a full URL (``https://connect.prusa3d.com/login/auth-callback?...``)
    or just the query string (``code=...&state=...``).
    """
    s = url.strip()
    # Tolerate users pasting just the query, or a leading ``?``.
    if "://" in s:
        parsed = urllib.parse.urlparse(s)
        query = parsed.query
    else:
        query = s.lstrip("?")

    params = urllib.parse.parse_qs(query)
    error = params.get("error", [None])[0]
    if error:
        description = params.get("error_description", [""])[0]
        raise RuntimeError(f"OAuth authorization failed: {error} {description}".strip())

    code = params.get("code", [None])[0]
    if not code:
        raise RuntimeError("No 'code' parameter found in the pasted URL. Make sure you copied the full address.")
    state = params.get("state", [None])[0]
    return code, state


def login_interactive() -> dict[str, Any]:  # noqa: C901
    """Run the PKCE flow inside an embedded webview, persist tokens, and return them.

    Flow:
        1. Generate PKCE + state and build the ``/o/authorize/`` URL using
           PrusaSlicer's public OAuth client + ``prusaslicer://login`` redirect.
        2. Open the URL inside a ``pywebview`` window. The user signs in to
           Prusa Account as normal (SSO, 2FA, passkeys are all supported —
           it's a real native webview).
        3. On success, Prusa Account redirects the webview to
           ``prusaslicer://login?code=...&state=...``. A background watcher
           thread polls the webview's current URL, captures the callback, and
           destroys the window before the OS hands the custom-scheme URL off
           to any real PrusaSlicer install.
        4. POST the code + PKCE verifier to ``/o/token/`` and save the result.

    Raises:
        RuntimeError: on any failure during authorization or token exchange.
    """
    try:
        import webview  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError(
            "The 'login' subcommand requires the 'pywebview' package. "
            "Run `uv sync` (or `pip install pywebview`) before retrying. "
            "On Linux you also need system WebKit2GTK (e.g. `apt install "
            "gir1.2-webkit2-4.1`)."
        ) from e

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    auth_params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    authorize_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(auth_params)}"

    # The webview runs on the main thread; the watcher runs on a background
    # thread started by ``webview.start``. We pass results back through this
    # mutable dict.
    captured: dict[str, str | None] = {"url": None, "error": None}

    def watcher(win: Any) -> None:
        """Poll the webview's current URL until it hits ``prusaslicer://login``."""
        deadline = time.monotonic() + 300.0  # 5 minutes should be plenty.
        while time.monotonic() < deadline:
            try:
                url = win.get_current_url()
            except Exception:  # noqa: BLE001
                url = None
            if url and url.startswith("prusaslicer://"):
                captured["url"] = url
                break
            time.sleep(0.1)
        else:
            captured["error"] = "Timed out (5 min) waiting for the OAuth callback."
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            logger.debug("webview destroy failed", exc_info=True)

    window = webview.create_window(
        title="Sign in to Prusa Account",
        url=authorize_url,
        width=520,
        height=760,
    )
    webview.start(watcher, window)

    if captured["error"]:
        raise RuntimeError(captured["error"])
    callback_url = captured["url"]
    if not callback_url:
        raise RuntimeError("Login window was closed before a callback was received.")

    code, returned_state = _extract_code_from_url(callback_url)
    if returned_state != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF, aborting.")

    # Exchange the code for tokens. Must match the redirect_uri used above.
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
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
    # a new one in the response. Persist whatever we got back — unless the
    # token file was deleted out from under us while the refresh was in flight
    # (e.g. the host cleared tokens on a shared volume), in which case
    # resurrecting the file would silently undo the user's action.
    path = _default_token_path()
    if path.exists():
        _save_tokens(new_tokens)
    else:
        logger.info("Token file was removed during refresh; not persisting new tokens.")
        raise LoginRequired(
            "Token file was cleared during refresh. Run `prusa-mcp login` to re-authenticate."
        )
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
        # Drop the in-memory cache if the token file has been removed out from
        # under us (e.g. the host cleared tokens on a shared volume). Without
        # this check we would happily keep serving requests with the cached
        # access token — and a later refresh would resurrect the deleted file.
        if _cached is not None and not _default_token_path().exists():
            logger.info("Token file disappeared; dropping in-memory cache.")
            _cached = None

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
