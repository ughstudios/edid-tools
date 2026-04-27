from __future__ import annotations

import base64
import ctypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from ctypes import wintypes
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from edid.logging_utils import log_exception, log_notice


PROJECT_TRACKER_URL = "https://tracker.colorlightcloud.com"


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
    normalized_email = email.strip().lower()
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    try:
        csrf = _fetch_csrf(opener)
        _post_credentials(opener, normalized_email, password, csrf)
        user = _fetch_current_user(opener)
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise IssueTrackerAuthError(f"Project-tracker login failed: HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise IssueTrackerAuthError(f"Could not reach project-tracker: {exc}") from exc
    except TimeoutError as exc:
        raise IssueTrackerAuthError("Project-tracker authentication timed out.") from exc

    if not user:
        return IssueTrackerAuthResult(ok=False, error="Invalid credentials or account is not approved.")
    return IssueTrackerAuthResult(
        ok=True,
        name=user.get("name"),
        email=user.get("email") or normalized_email,
        role=user.get("role"),
    )


def _fetch_csrf(opener: object) -> str:
    request = Request(f"{PROJECT_TRACKER_URL}/api/auth/csrf", headers={"Accept": "application/json"})
    with opener.open(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("csrfToken")
    if not token:
        raise IssueTrackerAuthError("Project-tracker did not return a CSRF token.")
    return str(token)


def _post_credentials(opener: object, email: str, password: str, csrf: str) -> None:
    body = urlencode(
        {
            "csrfToken": csrf,
            "email": email,
            "password": password,
            "redirect": "false",
            "callbackUrl": f"{PROJECT_TRACKER_URL}/",
            "json": "true",
        }
    ).encode("utf-8")
    request = Request(
        f"{PROJECT_TRACKER_URL}/api/auth/callback/credentials",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Colorlight EDID Tools",
        },
        method="POST",
    )
    with opener.open(request, timeout=20) as response:
        payload_text = response.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(payload_text) if payload_text else {}
    except json.JSONDecodeError:
        payload = {}
    if payload.get("error"):
        raise IssueTrackerAuthError("Invalid credentials or account is not approved.")


def _fetch_current_user(opener: object) -> dict[str, str] | None:
    request = Request(f"{PROJECT_TRACKER_URL}/api/me", headers={"Accept": "application/json"})
    with opener.open(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    user = payload.get("user") if isinstance(payload, dict) else None
    if isinstance(user, dict) and user.get("email"):
        return {key: str(value) for key, value in user.items() if value is not None}
    if isinstance(payload, dict) and payload.get("email"):
        return {key: str(value) for key, value in payload.items() if value is not None}
    return None


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

