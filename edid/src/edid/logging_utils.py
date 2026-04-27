from __future__ import annotations

from datetime import datetime
import traceback


def log_event(event: str, **fields: object) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    details = " ".join(f"{key}={value!r}" for key, value in fields.items())
    print(f"[{timestamp}] {event}" + (f" | {details}" if details else ""), flush=True)


def log_notice(event: str, **fields: object) -> None:
    log_event(f"Notice: {event}", **fields)


def log_exception(event: str, exc: BaseException, **fields: object) -> None:
    log_event(event, error=str(exc) or type(exc).__name__, **fields)
    traceback.print_exception(type(exc), exc, exc.__traceback__)
