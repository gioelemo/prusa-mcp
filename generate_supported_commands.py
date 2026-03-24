"""Generate supported_command.md from supported_command.json.

Usage:
    python generate_supported_commands.py
"""

import json
from pathlib import Path

# Category definitions: (category name, list of command names)
CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "Print Control",
        [
            "SET_PRINTER_READY",
            "CANCEL_PRINTER_READY",
            "START_PRINT",
            "PAUSE_PRINT",
            "RESUME_PRINT",
            "STOP_PRINT",
            "CANCEL_OBJECT",
        ],
    ),
    (
        "Movement",
        [
            "HOME",
            "MOVE",
            "MOVE_Z",
            "MOVE_E",
            "MESH_BED_LEVELING",
            "DISABLE_STEPPERS",
        ],
    ),
    (
        "Temperature & Print Settings",
        [
            "SET_NOZZLE_TEMPERATURE",
            "SET_HEATBED_TEMPERATURE",
            "SET_SPEED",
            "SET_FLOW",
        ],
    ),
    (
        "Filament",
        [
            "LOAD_FILAMENT",
            "UNLOAD_FILAMENT",
        ],
    ),
    (
        "File & Folder Management",
        [
            "SEND_FILE_INFO",
            "DELETE_FILE",
            "DELETE_FOLDER",
            "CREATE_FOLDER",
        ],
    ),
    (
        "Transfers & Downloads",
        [
            "START_CONNECT_DOWNLOAD",
            "START_ENCRYPTED_DOWNLOAD",
            "SEND_TRANSFER_INFO",
            "STOP_TRANSFER",
        ],
    ),
    (
        "Job Management",
        [
            "SEND_JOB_INFO",
        ],
    ),
    (
        "Tool & Nozzle Configuration",
        [
            "SET_TOOL_NOZZLE_DIAMETER",
            "SET_TOOL_HARDENED",
            "SET_TOOL_HIGH_FLOW",
        ],
    ),
    (
        "Enclosure",
        [
            "SET_ENCLOSURE_ENABLED",
            "SET_ENCLOSURE_PRINTING_FILTRATION",
            "SET_ENCLOSURE_POSTPRINT",
            "SET_ENCLOSURE_POSTPRINT_FILTRATION_TIME",
        ],
    ),
    (
        "Printer Info & State",
        [
            "SEND_INFO",
            "SEND_STATE_INFO",
            "SET_TOKEN",
            "SET_HOSTNAME",
            "DIALOG_ACTION",
        ],
    ),
    (
        "Printer Reset & Firmware",
        [
            "RESET_PRINTER",
            "RESET",
            "UPGRADE",
            "FLASH",
        ],
    ),
    (
        "Miscellaneous",
        [
            "BEEP",
        ],
    ),
]


def _format_states(states: list[str]) -> str:
    """Format executable_from_state as comma-separated inline code."""
    return ", ".join(f"`{s}`" for s in states)


def _format_arg_row(arg: dict) -> str:
    """Build a markdown table row for one argument."""
    name = f"`{arg['name']}`"
    typ = f"`{arg['type']}`"
    req = "Yes" if arg.get("required") else "No"
    desc = arg.get("description", "")

    # Append unit if present
    unit = arg.get("unit")
    if unit:
        desc += f" ({unit})"

    # Append limits if present
    limits = []
    if "min_limit" in arg:
        limits.append(f"min: {arg['min_limit']}")
    if "max_limit" in arg:
        limits.append(f"max: {arg['max_limit']}")
    if limits:
        desc += f" [{', '.join(limits)}]"

    # Append default if present
    if "default" in arg:
        desc += f". Default: `{arg['default']}`"

    return f"| {name} | {typ} | {req} | {desc} |"


def _render_command(cmd: dict) -> list[str]:
    """Render a single command section."""
    lines: list[str] = []
    name = cmd["command"]
    desc = cmd.get("description", "")

    lines.append(f"### `{name}`")
    lines.append("")
    lines.append(desc)
    lines.append("")

    # Metadata
    states = cmd.get("executable_from_state", [])
    if states:
        lines.append(f"**States:** {_format_states(states)}")

    template = cmd.get("template")
    if template:
        gcode = template.replace("\r\n", " → ")
        lines.append(f"**G-code:** `{gcode}`")

    min_temp = cmd.get("min_temp_nozzle_e")
    if min_temp is not None:
        lines.append(f"**Min nozzle temp:** {min_temp} °C")

    if cmd.get("duplicates_allowed"):
        lines.append("**Duplicates allowed:** Yes")

    # Args table
    args = cmd.get("args", [])
    if args:
        lines.append("")
        lines.append("| Argument | Type | Required | Description |")
        lines.append("|----------|------|----------|-------------|")
        for arg in args:
            lines.append(_format_arg_row(arg))

    lines.append("")
    return lines


def generate(json_path: Path, md_path: Path) -> None:
    """Read JSON and write formatted markdown."""
    with json_path.open() as f:
        data = json.load(f)

    commands = data["commands"]
    cmd_map = {c["command"]: c for c in commands}

    lines: list[str] = []

    # Header
    lines.append("# Prusa Connect — Command Reference")
    lines.append("")
    lines.append(
        "> **Warning:** This reference was auto-generated from reverse-engineered "
        "Prusa Connect commands. This is **not an official API** — commands were "
        "extracted by inspecting network traffic and may be incomplete or inaccurate. "
        "Not all commands have been tested. Some may not work as expected or could "
        "cause unintended behavior — including potential damage to the printer. "
        "**Use at your own risk** and always verify commands in a safe environment "
        "before relying on them."
    )
    lines.append("")

    # Table of contents
    lines.append("## Table of Contents")
    lines.append("")
    for category, _ in CATEGORIES:
        anchor = category.lower().replace(" ", "-").replace("&", "")
        # Remove double dashes from anchor
        while "--" in anchor:
            anchor = anchor.replace("--", "-")
        lines.append(f"- [{category}](#{anchor})")
    lines.append("")

    # Render each category
    categorized: set[str] = set()
    for category, cmd_names in CATEGORIES:
        lines.append(f"## {category}")
        lines.append("")
        for name in cmd_names:
            if name not in cmd_map:
                continue
            categorized.add(name)
            lines.extend(_render_command(cmd_map[name]))

    # Catch any uncategorized commands
    uncategorized = [c for c in commands if c["command"] not in categorized]
    if uncategorized:
        lines.append("## Other")
        lines.append("")
        for cmd in uncategorized:
            lines.extend(_render_command(cmd))

    md_path.write_text("\n".join(lines))
    print(f"Generated {md_path} ({len(commands)} commands)")


if __name__ == "__main__":
    root = Path(__file__).parent
    generate(root / "supported_command.json", root / "supported_command.md")
