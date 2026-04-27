"""Generate XML-backed UI modules before controllers import them."""

from __future__ import annotations

from edid.ui_keys import ensure_ui_key_modules


def ensure_generated_ui_modules() -> None:
    ensure_ui_key_modules()


ensure_generated_ui_modules()

__all__ = ("ensure_generated_ui_modules",)
