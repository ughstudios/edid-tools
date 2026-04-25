from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .edid_data import DisplayData, DisplayDataError, load_display_data, save_display_data


REVIEW_TEXT = """\
Python remake review

Native hardware writer source tree:
  Added: EDID/DisplayID parsing, validation, checksum repair, BIN/DAT/TXT/INF conversion, and PySide GUI workflow.
  The risky part is direct monitor EEPROM access over AMD ADL and NVIDIA NVAPI I2C.

Native override editor source tree:
  Display overrides are stored under HKLM\\SYSTEM\\CurrentControlSet\\Enum\\DISPLAY, with companion actions
  to reset override keys, clear graphics-driver caches, and disable/enable display adapters.
  This Python rewrite exposes those operations as guarded CLI/GUI actions and includes recovery-mode restart.
"""


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except (DisplayDataError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edid_tools.py",
        description="Python-only EDID, DisplayID, and Windows display override tools.",
    )
    subparsers = parser.add_subparsers(dest="command")

    review = subparsers.add_parser("review", help="summarize what was remade from the native tools")
    review.set_defaults(func=cmd_review)

    info = subparsers.add_parser("info", help="inspect an EDID/DisplayID file")
    info.add_argument("input")
    info.set_defaults(func=cmd_info)

    structured_info = subparsers.add_parser("structured-info", help="inspect structured EDID blocks")
    structured_info.add_argument("input")
    structured_info.set_defaults(func=cmd_structured_info)

    convert = subparsers.add_parser("convert", help="convert EDID/DisplayID files between BIN, DAT, TXT, and INF")
    convert.add_argument("input")
    convert.add_argument("output")
    convert.add_argument("--format", choices=["auto", "bin", "dat", "txt", "inf"], default="auto")
    convert.set_defaults(func=cmd_convert)

    extract = subparsers.add_parser("extract-embedded", help="extract embedded EDID payloads from executable/resource files")
    extract.add_argument("input")
    extract.add_argument("output_prefix")
    extract.add_argument("--format", choices=["bin", "dat", "txt", "inf"], default="bin")
    extract.set_defaults(func=cmd_extract_embedded)

    fix = subparsers.add_parser("fix", help="repair EDID/DisplayID header, extension, and checksum issues")
    fix.add_argument("input")
    fix.add_argument("output")
    fix.add_argument("--format", choices=["auto", "bin", "dat", "txt", "inf"], default="auto")
    fix.set_defaults(func=cmd_fix)

    list_displays = subparsers.add_parser("list-displays", help="list Windows display registry instances")
    list_displays.add_argument("--json", action="store_true")
    list_displays.set_defaults(func=cmd_list_displays)

    export = subparsers.add_parser("export-display", help="export active or override EDID from Windows registry")
    export.add_argument("target", help="device id, product id, or DEVICE\\INSTANCE")
    export.add_argument("output")
    export.add_argument("--source", choices=["active", "override"], default="active")
    export.add_argument("--format", choices=["auto", "bin", "dat", "txt", "inf"], default="auto")
    export.set_defaults(func=cmd_export_display)

    hardware = subparsers.add_parser("list-hardware", help="list AMD/NVIDIA DDC-capable displays")
    hardware.add_argument("--status", action="store_true", help="show AMD/NVIDIA backend availability")
    hardware.set_defaults(func=cmd_list_hardware)

    read_hardware = subparsers.add_parser("read-hardware", help="read EDID or DisplayID directly over GPU DDC/I2C")
    read_hardware.add_argument("target", help="hardware display key or product id")
    read_hardware.add_argument("output")
    read_hardware.add_argument("--kind", choices=["edid", "displayid"], default="edid")
    read_hardware.add_argument("--format", choices=["auto", "bin", "dat", "txt", "inf"], default="auto")
    read_hardware.set_defaults(func=cmd_read_hardware)

    write_hardware = subparsers.add_parser("write-hardware", help="write EDID or DisplayID directly over GPU DDC/I2C")
    write_hardware.add_argument("target", help="hardware display key or product id")
    write_hardware.add_argument("input")
    write_hardware.add_argument("--kind", choices=["edid", "displayid"], default="edid")
    write_hardware.add_argument("--fix", action="store_true", help="repair data before writing")
    write_hardware.add_argument("--allow-invalid", action="store_true", help="allow invalid checksums")
    write_hardware.add_argument("--yes", action="store_true", help="confirm physical display EEPROM write")
    write_hardware.set_defaults(func=cmd_write_hardware)

    install = subparsers.add_parser("install-override", help="install an EDID override in Windows registry")
    install.add_argument("input")
    install.add_argument("--target", help="device id, product id, DEVICE\\INSTANCE, or all")
    install.add_argument("--fix", action="store_true", help="repair EDID issues before installing")
    install.add_argument("--allow-invalid", action="store_true", help="allow invalid checksums")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--yes", action="store_true", help="confirm registry writes")
    install.set_defaults(func=cmd_install_override)

    reset_display = subparsers.add_parser("reset-display", help="remove EDID data/overrides for a target display")
    reset_display.add_argument("--target", default="all", help="device id, product id, DEVICE\\INSTANCE, or all")
    reset_display.add_argument("--dry-run", action="store_true")
    reset_display.add_argument("--yes", action="store_true", help="confirm registry writes")
    reset_display.set_defaults(func=cmd_reset_display)

    reset_all = subparsers.add_parser("reset-all", help="reset all display overrides and graphics cache keys")
    reset_all.add_argument("--dry-run", action="store_true")
    reset_all.add_argument("--yes", action="store_true", help="confirm registry writes")
    reset_all.set_defaults(func=cmd_reset_all)

    restart = subparsers.add_parser("restart-driver", help="disable and re-enable display adapters")
    restart.add_argument(
        "--mode",
        choices=["normal", "recovery"],
        default="normal",
        help="normal restart or restart with temporary EDID recovery staging",
    )
    restart.add_argument("--quiet", "-q", action="store_true", help="run without success output, matching restart.exe /q")
    restart.add_argument("--yes", action="store_true", help="confirm driver restart")
    restart.set_defaults(func=cmd_restart_driver)

    gui = subparsers.add_parser("gui", help="launch the PySide desktop UI")
    gui.set_defaults(func=cmd_gui)

    return parser


def cmd_review(_args: argparse.Namespace) -> int:
    print(REVIEW_TEXT.rstrip())
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    display_data = load_display_data(args.input)
    for line in display_data.summary_lines():
        print(line)
    warnings = display_data.warnings()
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  {warning}")
    return 0


def cmd_structured_info(args: argparse.Namespace) -> int:
    from .displayid import DisplayIDDocument
    from .structured_edid import StructuredEDID

    display_data = load_display_data(args.input)
    if display_data.is_displayid:
        lines = DisplayIDDocument.parse(display_data).summary_lines()
    else:
        lines = StructuredEDID.parse(display_data).summary_lines()
    for line in lines:
        print(line)
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    display_data = load_display_data(args.input)
    save_display_data(display_data, args.output, args.format)
    print(f"Wrote {args.output}")
    return 0


def cmd_extract_embedded(args: argparse.Namespace) -> int:
    from .cru_import_export import extract_edids_from_binary

    raw = Path(args.input).read_bytes()
    matches = extract_edids_from_binary(raw)
    if not matches:
        raise DisplayDataError("No embedded EDID payloads found.")
    prefix = Path(args.output_prefix)
    for index, display_data in enumerate(matches, start=1):
        suffix = args.format
        path = prefix.with_name(f"{prefix.name}-{index}.{suffix}")
        save_display_data(display_data, path, args.format)
        print(f"Wrote {path}")
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    display_data = load_display_data(args.input, trim=False)
    fixed = display_data.auto_fix()
    save_display_data(fixed, args.output, args.format)
    print(f"Wrote repaired data to {args.output}")
    for warning in fixed.warnings():
        print(f"  {warning}")
    return 0


def cmd_list_displays(args: argparse.Namespace) -> int:
    from . import windows_display

    displays = windows_display.list_display_instances()
    if args.json:
        print(json.dumps([_display_to_json(display) for display in displays], indent=2))
        return 0
    if not displays:
        print("No display registry instances found.")
        return 0
    for display in displays:
        print(display.label())
    return 0


def cmd_export_display(args: argparse.Namespace) -> int:
    from . import windows_display

    display_data = windows_display.export_display_data(args.target, source=args.source)
    save_display_data(display_data, args.output, args.format)
    print(f"Wrote {args.source} EDID to {args.output}")
    return 0


def cmd_list_hardware(_args: argparse.Namespace) -> int:
    from . import hardware_display

    if _args.status:
        for status in hardware_display.hardware_backend_status():
            state = "available" if status.available else "unavailable"
            print(f"{status.backend}: {state}; displays={status.display_count}; {status.message}")
        return 0
    displays = hardware_display.list_hardware_displays()
    if not displays:
        print("No AMD/NVIDIA DDC-capable displays found.")
        return 0
    for display in displays:
        print(display.label())
    return 0


def cmd_read_hardware(args: argparse.Namespace) -> int:
    display = _find_hardware_display(args.target)
    data = display.read_displayid() if args.kind == "displayid" else display.read_edid()
    save_display_data(data, args.output, args.format)
    print(f"Wrote {args.kind.upper()} from {display.label()} to {args.output}")
    return 0


def cmd_write_hardware(args: argparse.Namespace) -> int:
    data = load_display_data(args.input, trim=False)
    if args.fix:
        data = data.auto_fix()
    if args.kind == "edid":
        if not data.is_edid:
            raise DisplayDataError("Input is not EDID data.")
        if not args.allow_invalid and not data.has_valid_edid_checksums():
            raise DisplayDataError("EDID checksum is invalid. Re-run with --fix or --allow-invalid.")
    else:
        if not data.is_displayid:
            raise DisplayDataError("Input is not DisplayID data.")
        if not args.allow_invalid and not data.has_valid_displayid_checksums():
            raise DisplayDataError("DisplayID checksum is invalid. Re-run with --fix or --allow-invalid.")
    _require_confirmation(args.yes, f"write {args.kind.upper()} directly to physical display EEPROM")
    display = _find_hardware_display(args.target)
    if args.kind == "displayid":
        display.write_and_verify_displayid(data)
    else:
        display.write_and_verify_edid(data)
    print(f"Wrote and verified {args.kind.upper()} on {display.label()}")
    return 0


def cmd_install_override(args: argparse.Namespace) -> int:
    from . import windows_display

    display_data = load_display_data(args.input, trim=False)
    if args.fix:
        display_data = display_data.auto_fix()
    if not args.dry_run:
        _require_confirmation(args.yes, "install an EDID override in HKLM")
        _require_admin(windows_display)
    matches = windows_display.install_edid_override(
        display_data,
        target=args.target,
        allow_invalid=args.allow_invalid,
        dry_run=args.dry_run,
    )
    action = "Would install" if args.dry_run else "Installed"
    for display in matches:
        print(f"{action}: {display.label()}")
    if not args.dry_run:
        print("Restart the display driver or reboot for Windows to redetect displays.")
    return 0


def cmd_reset_display(args: argparse.Namespace) -> int:
    from . import windows_display

    if not args.dry_run:
        _require_confirmation(args.yes, f"reset display registry data for {args.target}")
        _require_admin(windows_display)
    matches = windows_display.reset_display(args.target, dry_run=args.dry_run)
    action = "Would reset" if args.dry_run else "Reset"
    for display in matches:
        print(f"{action}: {display.label()}")
    if not args.dry_run:
        print("Restart the display driver or reboot for Windows to redetect displays.")
    return 0


def cmd_reset_all(args: argparse.Namespace) -> int:
    from . import windows_display

    if not args.dry_run:
        _require_confirmation(args.yes, "reset all display overrides and graphics cache keys")
        _require_admin(windows_display)
    summary = windows_display.reset_all(dry_run=args.dry_run)
    prefix = "Would reset" if args.dry_run else "Reset"
    print(f"{prefix}: {summary}")
    if not args.dry_run:
        print("Restart the display driver or reboot for Windows to redetect displays.")
    return 0


def cmd_restart_driver(args: argparse.Namespace) -> int:
    from . import windows_display

    _require_confirmation(args.yes, "restart display adapters")
    _require_admin(windows_display)
    if args.quiet:
        result = windows_display.restart_display_driver_quiet(recovery=args.mode == "recovery")
        if not args.quiet:
            print(f"Restarted display driver: {result}")
    elif args.mode == "recovery":
        result = windows_display.restart_display_driver_recovery()
        print(f"Restarted display driver in recovery mode: {result}")
    else:
        disabled, enabled = windows_display.restart_display_driver()
        print(f"Restarted display driver: disabled {disabled}, enabled {enabled}.")
    return 0


def cmd_gui(_args: argparse.Namespace) -> int:
    from .elevation import ensure_gui_elevated
    from .gui import run_gui

    if not ensure_gui_elevated():
        return 0
    return run_gui()


def _display_to_json(display: object) -> dict[str, object]:
    active_data = getattr(display, "active_data")
    override_data = getattr(display, "override_data")
    return {
        "key": getattr(display, "key"),
        "device_id": getattr(display, "device_id"),
        "instance_id": getattr(display, "instance_id"),
        "name": getattr(display, "name"),
        "product_id": getattr(display, "product_id"),
        "has_active_edid": bool(active_data),
        "has_override": bool(override_data),
        "active_size": active_data.size if active_data else None,
        "override_size": override_data.size if override_data else None,
    }


def _find_hardware_display(target: str) -> object:
    from . import hardware_display

    normalized = target.strip().upper()
    displays = hardware_display.list_hardware_displays()
    for display in displays:
        candidates = {display.key.upper()}
        if display.product_id:
            candidates.add(display.product_id.upper())
        if normalized in candidates:
            return display
    raise RuntimeError(f"No hardware display matched {target!r}.")


def _require_confirmation(yes: bool, action: str) -> None:
    if yes:
        return
    raise RuntimeError(f"Refusing to {action} without --yes. Use --dry-run first if you want a preview.")


def _require_admin(windows_display: object) -> None:
    if not windows_display.is_admin():
        raise RuntimeError("Administrator privileges are required for this Windows operation.")
