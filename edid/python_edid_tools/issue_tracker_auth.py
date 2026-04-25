from __future__ import annotations

import base64
import ctypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
from ctypes import wintypes
from .logging_utils import log_exception, log_notice


class IssueTrackerAuthError(RuntimeError):
    """Raised when project-tracker authentication cannot be completed."""


@dataclass
class IssueTrackerAuthResult:
    ok: bool
    name: str | None = None
    email: str | None = None
    role: str | None = None
    error: str | None = None


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def authenticate_issue_tracker_user(email: str, password: str) -> IssueTrackerAuthResult:
    issue_tracker_dir = _find_issue_tracker_dir()
    if not issue_tracker_dir:
        raise IssueTrackerAuthError("Could not find the project-tracker app folder.")

    script = r"""
const fs = require("fs");
const path = require("path");
const dotenv = require("dotenv");

for (const name of [".env.local", ".env"]) {
  const file = path.join(process.cwd(), name);
  if (fs.existsSync(file)) dotenv.config({ path: file });
}

const bcrypt = require("bcryptjs");
const { PrismaClient } = require("./src/generated/prisma");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => input += chunk);
process.stdin.on("end", async () => {
  const prisma = new PrismaClient();
  try {
    const { email, password } = JSON.parse(input || "{}");
    const normalizedEmail = String(email || "").trim().toLowerCase();
    const user = await prisma.user.findUnique({ where: { email: normalizedEmail } });
    if (!user || user.approvalStatus !== "APPROVED") {
      console.log(JSON.stringify({ ok: false, error: "Invalid credentials or account is not approved." }));
      return;
    }
    const valid = await bcrypt.compare(String(password || ""), user.passwordHash);
    if (!valid) {
      console.log(JSON.stringify({ ok: false, error: "Invalid credentials or account is not approved." }));
      return;
    }
    console.log(JSON.stringify({ ok: true, name: user.name, email: user.email, role: user.role }));
  } catch (error) {
    console.log(JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) }));
  } finally {
    await prisma.$disconnect();
  }
});
"""
    try:
        completed = subprocess.run(
            ["node", "-e", script],
            input=json.dumps({"email": email, "password": password}),
            cwd=str(issue_tracker_dir),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise IssueTrackerAuthError("Node.js is required to authenticate against project-tracker login.") from exc
    except subprocess.TimeoutExpired as exc:
        raise IssueTrackerAuthError("Project-tracker authentication timed out.") from exc

    output = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    if not output:
        message = completed.stderr.strip() or "Project-tracker authentication returned no result."
        raise IssueTrackerAuthError(message)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise IssueTrackerAuthError(output) from exc
    return IssueTrackerAuthResult(
        ok=bool(payload.get("ok")),
        name=payload.get("name"),
        email=payload.get("email"),
        role=payload.get("role"),
        error=payload.get("error"),
    )


def save_cached_auth(result: IssueTrackerAuthResult) -> None:
    if not result.ok or not result.email:
        return
    payload = {
        "email": result.email,
        "name": result.name,
        "role": result.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _auth_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = _protect_bytes(json.dumps(payload).encode("utf-8"))
    path.write_text(base64.b64encode(protected).decode("ascii"), encoding="ascii")


def load_cached_auth(*, max_age_days: int = 30) -> IssueTrackerAuthResult | None:
    path = _auth_cache_path()
    if not path.exists():
        return None
    try:
        protected = base64.b64decode(path.read_text(encoding="ascii"))
        payload = json.loads(_unprotect_bytes(protected).decode("utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"])
        if datetime.now(timezone.utc) - created_at > timedelta(days=max_age_days):
            clear_cached_auth()
            return None
        return IssueTrackerAuthResult(
            ok=True,
            name=payload.get("name"),
            email=payload.get("email"),
            role=payload.get("role"),
        )
    except Exception as exc:
        log_exception("Cached project-tracker auth load failed", exc)
        clear_cached_auth()
        return None


def clear_cached_auth() -> None:
    path = _auth_cache_path()
    try:
        path.unlink()
    except FileNotFoundError as exc:
        log_notice("Cached project-tracker auth file not found while clearing", error=exc)
        pass


def _auth_cache_path() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "ColorlightEdidTools" / "eeprom_auth.dat"


def _protect_bytes(data: bytes) -> bytes:
    if os.name != "nt":
        return data
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DATA_BLOB(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)):
        raise IssueTrackerAuthError("Failed to protect local auth cache.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _unprotect_bytes(data: bytes) -> bytes:
    if os.name != "nt":
        return data
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DATA_BLOB(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)):
        raise IssueTrackerAuthError("Failed to read local auth cache.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _find_issue_tracker_dir() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "issue-tracker"
        if (candidate / "package.json").exists() and (candidate / "src/generated/prisma").exists():
            return candidate
        sibling = parent.parent / "issue-tracker"
        if (sibling / "package.json").exists() and (sibling / "src/generated/prisma").exists():
            return sibling
    return None
