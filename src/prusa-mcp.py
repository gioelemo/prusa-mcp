import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
from playwright.async_api import TimeoutError as PWTimeoutError
from playwright.async_api import async_playwright  # type: ignore[import-not-found]

# Load environment variables from .env file
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("prusa-printer")
logger = logging.getLogger(__name__)


# Constants
PRUSA_API_BASE = "https://connect.prusa3d.com/app"
CONNECT_URL = os.environ.get("PRUSA_CONNECT_URL", "https://connect.prusa3d.com")

# Where we persist session cookies (storage_state). Keep this private!
STATE_FILE = os.environ.get("PRUSA_CONNECT_STATE", "connect_state.json")

# Headless by default; set HEADLESS=0 to watch the browser
HEADLESS = os.environ.get("HEADLESS", "1") != "0"

# Optional: Enable Playwright tracing for debugging (stores trace.zip)
ENABLE_TRACING = os.environ.get("PW_TRACING", "0") == "1"

# Reasonable default timeouts (ms)
NAV_TIMEOUT = int(os.environ.get("PW_NAV_TIMEOUT_MS", "30000"))
SEL_TIMEOUT = int(os.environ.get("PW_SEL_TIMEOUT_MS", "15000"))


# ----------------------------
# Utility: open a browser context
# ----------------------------
async def _open_context():
    """
    Launch Chromium and return (playwright, browser, context).
    If STATE_FILE exists, we reuse it (keeps you logged in).
    """
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=HEADLESS)
    storage_state = STATE_FILE if Path(STATE_FILE).exists() else None
    context = await browser.new_context(storage_state=storage_state)
    if ENABLE_TRACING:
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
    return p, browser, context


async def _close_context(p, browser, context, *, save_state=True):
    """
    Optionally save storage_state for persistent sessions.
    """
    try:
        if ENABLE_TRACING:
            await context.tracing.stop(path="trace.zip")
        if save_state:
            await context.storage_state(path=STATE_FILE)
    finally:
        await browser.close()
        await p.stop()


# ----------------------------
# Core login flow
# ----------------------------
async def ensure_login(email: str | None, password: str | None) -> None:
    """
    Navigate to Connect, and if not already authenticated, perform the login flow.
    - If STATE_FILE already contains a valid session, this is a no-op.
    - Otherwise, we require email+password to log in.
    """
    p, browser, context = await _open_context()
    page = await context.new_page()
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    await page.goto(CONNECT_URL, wait_until="domcontentloaded")

    if await _is_already_logged_in(page):
        await _close_context(p, browser, context)
        return

    if not email or not password:
        await _close_context(p, browser, context, save_state=False)
        raise RuntimeError

    try:
        await _perform_login(page, email, password)

        if not await _is_already_logged_in(page):
            raise RuntimeError
    except PWTimeoutError as e:
        raise RuntimeError from e
    finally:
        await _close_context(p, browser, context)


async def _is_already_logged_in(page) -> bool:
    """Check if user is already authenticated."""
    content = await page.content()
    title = await page.title()
    return (
        "Sign in" not in content
        and "Log in" not in content
        and "Sign in" not in title
        and "Log in" not in title
    )


async def _perform_login(page, email: str, password: str) -> None:
    """Execute the complete login flow."""
    await _click_login_button(page)
    await page.wait_for_timeout(1500)  # Give the modal/form time to render

    email_field = await _find_email_field(page)
    password_field = await _find_password_field(page)

    await email_field.fill(email)
    await password_field.fill(password)
    await page.wait_for_timeout(500)  # Let fields register

    await _submit_login_form(page, password_field)
    await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)


async def _click_login_button(page) -> None:
    """Find and click the login button on the landing page."""
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1000)

    login_button_selectors = [
        "text='Log in or Sign up'",
        "text='Log in'",
        "text='Sign in'",
        "button:has-text('Log in')",
        "button:has-text('Sign up')",
        "a:has-text('Log in')",
        "a:has-text('Sign up')",
    ]

    if not await _try_click_selectors(page, login_button_selectors):
        raise RuntimeError


async def _find_email_field(page):
    """Locate the email input field."""
    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[name='username']",
        "input[id='email']",
        "input[placeholder*='mail' i]",
        "input[placeholder*='username' i]",
    ]

    field = await _try_find_field(page, email_selectors)
    if field is None:
        with suppress(Exception):
            field = page.get_by_label("Email", exact=False).first

    if field is None:
        raise RuntimeError

    return field


async def _find_password_field(page):
    """Locate the password input field."""
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[id='password']",
    ]

    field = await _try_find_field(page, password_selectors)
    if field is None:
        with suppress(Exception):
            field = page.get_by_label("Password", exact=False).first

    if field is None:
        raise RuntimeError

    return field


async def _submit_login_form(page, password_field) -> None:
    """Find and click the submit button, or press Enter as fallback."""
    button_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
        "button:has-text('Login')",
        "button:has-text('Continue')",
        "form button",
    ]

    if await _try_click_selectors(page, button_selectors):
        return

    # Fallback strategies
    try:
        await page.get_by_role("button").first.click()
    except Exception:
        await password_field.press("Enter")


async def _try_click_selectors(page, selectors: list[str]) -> bool:
    """Try clicking elements matching the given selectors. Returns True if successful."""
    for selector in selectors:
        try:
            element = page.locator(selector).first
            if await element.is_visible(timeout=2000):
                await element.click()
                return True
        except Exception:
            continue
    return False


async def _try_find_field(page, selectors: list[str]):
    """Try finding a field matching the given selectors. Returns None if not found."""
    for selector in selectors:
        try:
            field = page.locator(selector).first
            if await field.is_visible(timeout=2000):
                return field
        except Exception:
            continue
    return None


def _get_session_cookies() -> dict[str, str]:
    """
    Extract cookies from the stored session state file.
    Returns a dict suitable for httpx requests.
    """
    if not Path(STATE_FILE).exists():
        return {}

    try:
        with Path(STATE_FILE).open() as f:
            state = json.load(f)

        cookies = {}
        for cookie in state.get("cookies", []):
            cookies[cookie["name"]] = cookie["value"]
    except Exception:
        logger.exception("Failed to read session cookies")
        return {}
    else:
        return cookies


async def make_prusa_request(endpoint: str) -> dict[str, Any] | None:
    """Make a request to the Prusa Connect API using session cookies."""
    url = f"{PRUSA_API_BASE}{endpoint}"

    # Get cookies from stored session
    cookies = _get_session_cookies()

    if not cookies:
        logger.error(
            "No session cookies found. Please log in first using connect_login."
        )
        return None

    headers = {
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(cookies=cookies) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.exception("API request failed")
            return None


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

        # Try to extract some meta info when present
        meta = f.get("meta") or {}
        est = meta.get("estimated_printing_time_normal_mode") or meta.get(
            "estimated_print_time"
        )

        lines.append(
            f"{name} ({ftype}) - {path} - size={size} bytes - mtime={mtime} - est={est}"
        )

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

        lines.append(
            f"{name} ({stype}) mounted at {mount} - free={free} bytes - files={fcount} - read_only={ro}"
        )

    return "\n".join(lines)


@mcp.tool()
async def send_printer_command(
    printer_uuid: str, command: str, args: dict[str, Any] | None = None
) -> str:
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

    # Build command payload
    payload: dict[str, Any] = {"command": command}

    # Add args if provided
    if args:
        payload["args"] = args

    try:
        cookies = _get_session_cookies()
        async with httpx.AsyncClient(cookies=cookies, timeout=30.0) as client:
            url = f"{PRUSA_API_BASE}{endpoint}"

            logger.info(f"Sending command to {url}: {payload}")

            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()
            result = response.json()

            return f"Command '{command}' sent successfully to printer {printer_uuid}.\nResponse: {json.dumps(result, indent=2)}"

    except httpx.HTTPStatusError as e:
        logger.exception("HTTP error sending command")
        return (
            f"Failed to send command: HTTP {e.response.status_code} - {e.response.text}"
        )
    except Exception as e:
        logger.exception("Error sending command")
        return f"Error sending command: {e!s}"


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

    # Add temperature info if available
    if "temp" in printer:
        temp = printer["temp"]
        status += f"""
Temperature (Nozzle): {temp.get("temp_nozzle", "N/A")}°C (Target: {temp.get("target_nozzle", "N/A")}°C)
Temperature (Bed): {temp.get("temp_bed", "N/A")}°C (Target: {temp.get("target_bed", "N/A")}°C)
"""

    # Add job info if printing
    if "job_info" in printer:
        job = printer["job_info"]
        status += f"""
Current Job: {job.get("display_name", "Unknown")}
Progress: {job.get("progress", "N/A")}%
Time Printing: {job.get("time_printing", 0)} seconds
Time Remaining: {job.get("time_remaining", 0)} seconds
"""

    return status


@mcp.tool()
async def connect_login(email: str = "", password: str = "") -> str:
    """Log in to Prusa Connect and persist session cookies to reuse later.

    Args:
        email: Prusa Connect email / username (optional if set in environment as PRUSA_EMAIL)
        password: Prusa Connect password (optional if set in environment as PRUSA_PASSWORD)
    """
    try:
        # Use provided credentials or fall back to environment variables
        login_email = email or os.getenv("PRUSA_EMAIL")
        login_password = password or os.getenv("PRUSA_PASSWORD")

        if not login_email or not login_password:
            return "Error: Email and password must be provided either as arguments or via PRUSA_EMAIL and PRUSA_PASSWORD environment variables."

        await ensure_login(login_email, login_password)
    except Exception as e:
        logger.exception("Login failed")
        return f"Login failed: {e!s}"
    else:
        return f"Successfully logged in and session saved to {STATE_FILE}"


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

    printers = data.get("printers", [])  # Changed from "data" to "printers"
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
    # First get all printers and find the one with matching UUID
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
    # Note: Based on the API structure, you might need to adjust this endpoint
    # The exact jobs endpoint format may differ - check Prusa Connect API docs
    endpoint = f"/printers/{printer_uuid}/jobs?limit={limit}"
    data = await make_prusa_request(endpoint)

    if not data:
        return f"Unable to fetch jobs for printer {printer_uuid}."

    # Adjust based on actual API response structure
    jobs = data.get("jobs", []) or data.get("data", [])

    if not jobs:
        return "No jobs found for this printer."

    formatted_jobs = []
    for job in jobs:
        # Basic job fields
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
        # Cases handled:
        # - full http/https URLs: keep as-is
        # - protocol-relative URLs (//...): prefix with https:
        # - paths starting with /app: use PRUSA_API_BASE to avoid duplicating /app
        # - other paths starting with /: prefix with CONNECT_URL
        # - relative paths: prefix with CONNECT_URL
        if preview:
            try:
                p = str(preview).strip()
                # already absolute
                if p.startswith(("http://", "https://")):
                    preview = p
                elif p.startswith("//"):
                    preview = "https:" + p
                elif p.startswith("/app"):
                    # PRUSA_API_BASE already contains '/app'
                    preview = PRUSA_API_BASE.rstrip("/") + p[len("/app") :]
                elif p.startswith("/"):
                    preview = CONNECT_URL.rstrip("/") + p
                else:
                    # generic relative path
                    preview = CONNECT_URL.rstrip("/") + "/" + p.lstrip("/")
            except Exception:
                # If normalization fails for any reason, leave preview unchanged
                pass

        # Don't include preview in output as it doesn't render properly in Streamlit
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

        # Short representation of data if present
        data_repr = None
        if isinstance(data_field, dict):
            # pick a few keys to show
            keys = [
                k
                for k in ("target_nozzle", "target_bed", "path", "size")
                if k in data_field
            ]
            if keys:
                data_repr = ", ".join(f"{k}={data_field[k]}" for k in keys)
            else:
                data_repr = json.dumps(data_field)

        line = f"{evt} - {state} - source={source} - created={created} - server_time={server_time}"
        if data_repr:
            line += f" - data: {data_repr}"

        lines.append(line)

    return "\n".join(lines)


def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
