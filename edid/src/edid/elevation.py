from __future__ import annotations

from pathlib import Path
import ctypes
import os
import subprocess
import sys
from edid.logging_utils import log_exception


class ElevationError(RuntimeError):
    """Raised when Windows elevation cannot be requested."""


def is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError as exc:
        log_exception("Admin status check failed", exc)
        return False


def ensure_gui_elevated() -> bool:
    """Return True to continue; relaunch elevated and return False when needed."""
    if os.name != "nt" or is_admin():
        return True
    request_elevation_gui()
    return False


def request_elevation_gui() -> None:
    """Relaunch the GUI with UAC elevation using ShellExecuteW(..., 'runas', ...)."""
    if os.name != "nt":
        raise ElevationError("Elevation requests are only available on Windows.")

    executable = _python_executable()
    if getattr(sys, "frozen", False):
        parameters = "gui"
        working_directory = str(Path(sys.executable).resolve().parent)
    else:
        script = Path(__file__).resolve().parents[1] / "edid_tools.py"
        parameters = f'"{script}" gui'
        working_directory = str(script.parent)
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, parameters, working_directory, 1)
    if result <= 32:
        raise ElevationError(f"ShellExecuteW elevation request failed with code {result}.")


def _python_executable() -> str:
    current = Path(sys.executable)
    if current.name.lower() == "pythonw.exe":
        python = current.with_name("python.exe")
        if python.exists():
            return str(python)
    py_launcher = _where("py.exe")
    if py_launcher:
        return py_launcher
    return str(current)


def _where(name: str) -> str | None:
    try:
        completed = subprocess.run(["where", name], capture_output=True, text=True, check=False)
    except OSError as exc:
        log_exception("where command failed", exc, command=name)
        return None
    if completed.returncode != 0:
        return None
    lines = completed.stdout.strip().splitlines()
    return lines[0] if lines else None
