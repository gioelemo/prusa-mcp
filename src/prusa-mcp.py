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

    async def _looks_logged_in() -> bool:
        # Heuristic: if the page redirects to a dashboard with nav, or lacks sign-in UI.
        content = await page.content()
        title = await page.title()
        return (
            "Sign in" not in content
            and "Log in" not in content
            and "Sign in" not in title
            and "Log in" not in title
        )

    if await _looks_logged_in():
        await _close_context(p, browser, context)  # Already logged-in via STATE_FILE
        return

    # Need credentials to proceed
    if not email or not password:
        await _close_context(p, browser, context, save_state=False)
        raise RuntimeError

    # Attempt a robust login:
    try:
        # Step 1: Click the "Log in or Sign up" button on the landing page
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1000)  # Give the page time to render

        # Look for the "Log in or Sign up" button
        login_button_selectors = [
            "text='Log in or Sign up'",
            "text='Log in'",
            "text='Sign in'",
            "button:has-text('Log in')",
            "button:has-text('Sign up')",
            "a:has-text('Log in')",
            "a:has-text('Sign up')",
        ]

        clicked = False
        for selector in login_button_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=2000):
                    await button.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            raise RuntimeError

        # Step 2: Wait for login form/modal to appear
        await page.wait_for_timeout(1500)  # Give the modal/form time to render

        # Try multiple selectors for email field
        email_selectors = [
            "input[type='email']",
            "input[name='email']",
            "input[name='username']",
            "input[id='email']",
            "input[placeholder*='mail' i]",
            "input[placeholder*='username' i]",
        ]

        email_field = None
        for selector in email_selectors:
            try:
                email_field = page.locator(selector).first
                if await email_field.is_visible(timeout=2000):
                    break
            except Exception:
                continue

        if email_field is None:
            # Try label-based approach
            with suppress(Exception):
                email_field = page.get_by_label("Email", exact=False).first

        if email_field is None:
            raise RuntimeError

        # Try multiple selectors for password field
        password_selectors = [
            "input[type='password']",
            "input[name='password']",
            "input[id='password']",
        ]

        password_field = None
        for selector in password_selectors:
            try:
                password_field = page.locator(selector).first
                if await password_field.is_visible(timeout=2000):
                    break
            except Exception:
                continue

        if password_field is None:
            with suppress(Exception):
                password_field = page.get_by_label("Password", exact=False).first

        if password_field is None:
            raise RuntimeError

        # Fill in credentials
        await email_field.fill(email)
        await password_field.fill(password)

        # Give fields time to register (some sites check on blur)
        await page.wait_for_timeout(500)

        # Find and click the submit button - try multiple approaches
        submit_button = None
        button_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Sign in')",
            "button:has-text('Log in')",
            "button:has-text('Login')",
            "button:has-text('Continue')",
            "form button",
        ]

        for selector in button_selectors:
            try:
                submit_button = page.locator(selector).first
                if await submit_button.is_visible(timeout=1000):
                    await submit_button.click()
                    break
            except Exception:
                continue

        if submit_button is None:
            # Last resort: try role-based
            try:
                await page.get_by_role("button").first.click()
            except Exception:
                # Or just press Enter on the password field
                await password_field.press("Enter")

        # Wait until network idle meaning post-login redirects have settled
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

        if not await _looks_logged_in():
            raise RuntimeError
    except PWTimeoutError as e:
        raise RuntimeError from e
    finally:
        await _close_context(p, browser, context)


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
        job_info = f"""
Job ID: {job.get("id", "Unknown")}
File: {job.get("display_name", job.get("file_name", "Unknown"))}
Status: {job.get("status", job.get("state", "Unknown"))}
Started: {job.get("started_at", job.get("start", "Unknown"))}
Completed: {job.get("completed_at", "N/A")}
Progress: {job.get("progress", "N/A")}%
"""
        formatted_jobs.append(job_info)

    return "\n---\n".join(formatted_jobs)


def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
