#!/usr/bin/env python3
"""Slice an STL (or take a ready ``.bgcode``/``.gcode``) and print it via Prusa Connect.

Authenticate once, then this script just works::

    uv run prusa-mcp login

Examples::

    # See what's on the account and pick a target
    uv run examples/print_stl.py --list

    # Slice + upload + print
    uv run examples/print_stl.py cube.stl --config lab_xl.ini --printer "Printer 1"

    # Upload an already-sliced file without starting it
    uv run examples/print_stl.py cube.bgcode --printer "Printer 1" --no-print

    # Unattended: also dismiss the "unfinished selftest" warning
    uv run examples/print_stl.py cube.stl --config lab_xl.ini --auto-continue --yes

Slicing needs a local PrusaSlicer; set ``PRUSASLICER_CLI`` when it isn't on PATH.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys

# Allow running straight from a source checkout without installing the package.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from prusa_mcp import server  # noqa: E402
from prusa_mcp.oauth import get_access_token  # noqa: E402
from prusa_mcp.oauth import LoginRequired  # noqa: E402

# Only dialogs named here are ever dismissed automatically. Deliberately narrow:
# the same channel carries filament-runout, thermal-anomaly and crash-detected
# dialogs, which must be seen by a human.
AUTO_CONTINUE_KEYS = ["UNFINISHED_SELFTEST"]

SLICEABLE = {".stl", ".3mf", ".obj"}
PRINTABLE = {".gcode", ".bgcode"}


def describe(printer: dict) -> str:
    """Render one printer as a short two-line block."""
    temp = printer.get("temp") or {}
    job = (printer.get("job_info") or {}).get("display_name")
    return (
        f"  {printer.get('name'):<12} {printer.get('printer_state'):<10} {printer.get('printer_type_name', '')}\n"
        f"      uuid={printer.get('uuid')}  team={printer.get('team_id')}  location={printer.get('location')}\n"
        f"      nozzle={temp.get('temp_nozzle')}C bed={temp.get('temp_bed')}C" + (f"  job={job}" if job else "")
    )


def pick_printer(printers: list[dict], wanted: str | None) -> dict:
    """Select a printer by name or UUID, exiting with guidance when ambiguous."""
    if wanted:
        for printer in printers:
            if wanted in (printer.get("uuid"), printer.get("name")):
                return printer
        sys.exit(f"No printer matching {wanted!r}. Use --list to see the options.")
    if len(printers) == 1:
        return printers[0]
    sys.exit("Several printers available — pass --printer NAME_OR_UUID (see --list).")


def parse_args() -> argparse.Namespace:
    """Build and parse the command line."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("model", nargs="?", help="Input .stl/.3mf/.obj to slice, or a ready .gcode/.bgcode")
    parser.add_argument("--config", help="PrusaSlicer config bundle (.ini); required when slicing")
    parser.add_argument("--printer", help="Target printer name or UUID")
    parser.add_argument("--team", default="", help="Connect team id (auto-discovered when omitted)")
    parser.add_argument("--list", action="store_true", help="List printers and exit")
    parser.add_argument("--no-print", action="store_true", help="Upload only; do not start the print")
    parser.add_argument("--auto-continue", action="store_true", help=f"Auto-dismiss {AUTO_CONTINUE_KEYS}")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show HTTP logging")
    return parser.parse_args()


def configure_logging(*, verbose: bool) -> None:
    """Quieten per-request chatter unless the caller asked for it."""
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s: %(message)s")
    if not verbose:
        # httpx2 and the MCP SDK install their own handlers at import time.
        for noisy in ("httpx2", "httpcore2", "prusa_mcp.server", "prusa_mcp.oauth"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def resolve_inputs(model_arg: str, config_arg: str | None) -> tuple[str, str, str]:
    """Resolve and validate the paths, returning ``(model, suffix, config)``.

    Kept synchronous so the filesystem work stays off the event loop.
    """
    model = Path(model_arg).expanduser()
    if not model.is_file():
        sys.exit(f"File not found: {model}")
    suffix = model.suffix.lower()
    if suffix not in SLICEABLE | PRINTABLE:
        sys.exit(f"Don't know what to do with {suffix!r}")
    if suffix in SLICEABLE and not config_arg:
        sys.exit(f"{suffix} input needs --config (PrusaSlicer: File > Export > Export Config)")
    config = str(Path(config_arg).expanduser()) if config_arg else ""
    return str(model), suffix, config


async def report_job(printer_uuid: str) -> None:
    """Print a one-line summary of what the printer is doing now."""
    detail = await server.make_prusa_request(f"/printers/{printer_uuid}") or {}
    job = detail.get("job_info") or {}
    print(f"\nstate={detail.get('printer_state')} job={job.get('id')} remaining={job.get('time_remaining')}s")
    dialog = detail.get("dialog_info")
    if dialog:
        print(f"Printer is waiting on a dialog: {dialog.get('key')} — {dialog.get('text')}")


async def main() -> int:
    """Run the slice/upload/print pipeline described in the module docstring."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    try:
        await get_access_token()
    except LoginRequired as e:
        sys.exit(f"Not authenticated: {e}\nRun:  uv run prusa-mcp login")

    data = await server.make_prusa_request("/printers?limit=50")
    printers = (data or {}).get("printers", [])
    if not printers:
        sys.exit("No printers on this account.")

    if args.list or not args.model:
        print(f"{len(printers)} printer(s):")
        for printer in printers:
            print(describe(printer))
        return 0

    model, suffix, config = await asyncio.to_thread(resolve_inputs, args.model, args.config)

    printer = pick_printer(printers, args.printer)
    uuid = printer["uuid"]
    start = not args.no_print

    action = "slice + upload + PRINT" if start else "slice + upload"
    print(f"{action} on {printer['name']} ({printer.get('printer_state')}) — {printer.get('location')}")
    print(f"  file: {model}")
    if start and not args.yes:
        answer = await asyncio.to_thread(input, "  This moves a real printer. Continue? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            sys.exit("Aborted.")

    auto = AUTO_CONTINUE_KEYS if args.auto_continue else None

    if suffix in SLICEABLE:
        result = await server.slice_and_print(
            model,
            uuid,
            config,
            team_id=args.team,
            auto_continue_dialogs=auto,
            start_print=start,
        )
    else:
        result = await server.upload_gcode(
            model,
            uuid,
            team_id=args.team,
            auto_continue_dialogs=auto,
            start_print=start,
        )

    print(result)
    if start:
        await report_job(uuid)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
