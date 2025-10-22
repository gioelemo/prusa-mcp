from typing import Any
import httpx
import os
from mcp.server.fastmcp import FastMCP # type: ignore
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("prusa-printer")

# Constants
PRUSA_API_BASE = "https://connect.prusa3d.com/app"
ACCESS_TOKEN = os.getenv("PRUSA_ACCESS_TOKEN")

if not ACCESS_TOKEN:
    raise ValueError(
        "PRUSA_ACCESS_TOKEN not found in environment variables. Please add it to your .env file."
    )


async def make_prusa_request(endpoint: str) -> dict[str, Any] | None:
    """Make a request to the Prusa Connect API with proper error handling."""
    url = f"{PRUSA_API_BASE}{endpoint}"
    headers = {
        "Accept": "application/json",
        "Cookie": f"auth.access_token={ACCESS_TOKEN}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"API request failed: {e}")
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
    logging.info(data)

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
