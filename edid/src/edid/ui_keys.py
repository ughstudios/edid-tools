"""Bootstrap: fingerprint UI XML and emit generated `edid.ui.*` key modules."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from edid.ui_keys_emit import GENERATOR_VERSION, build_module_sources, module_name_from_root_filename
from edid.ui_xml_index import (
    UiXmlIndexError,
    collect_widget_names,
    collect_widget_types,
    fingerprint_root_xml,
    ui_anchor_dir,
)

_META_BASENAME = "ui_keys_generated.meta.json"
_META_VERSION = 8
_STANDALONE_ROOT_TAGS = {
    "widget",
    "tabs",
    "stack",
    "splitter",
    "QLabel",
    "QPushButton",
    "QComboBox",
    "QTextEdit",
    "QPlainTextEdit",
    "QLineEdit",
    "QCheckBox",
    "QSpinBox",
    "QListWidget",
    "QGroupBox",
    "QDialogButtonBox",
    "QScrollArea",
}


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _target_package_dir() -> Path:
    return _package_dir() / "ui"


def _assert_writable(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UiXmlIndexError(
            f"Cannot write generated UI modules in {path}. Make this directory writable."
        ) from exc


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _atomic_write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(path, text)


def _read_meta(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("version") != _META_VERSION:
        return None
    if data.get("generator_version") != GENERATOR_VERSION:
        return None
    roots = data.get("roots")
    if not isinstance(roots, dict):
        return None
    return data


def _discover_root_filenames(ui_dir: Path) -> tuple[str, ...]:
    filenames: list[str] = []
    for path in sorted(ui_dir.glob("*.xml"), key=lambda item: item.name):
        try:
            root_tag = ET.parse(path).getroot().tag
        except ET.ParseError as exc:
            raise UiXmlIndexError(f"Invalid UI XML in {path}: {exc}") from exc
        if root_tag in _STANDALONE_ROOT_TAGS:
            filenames.append(path.name)
    if not filenames:
        raise UiXmlIndexError(f"No loadable UI XML files found in {ui_dir}.")
    return tuple(filenames)


def _collect_all(
    ui_dir: Path,
    root_filenames: tuple[str, ...],
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], dict[str, dict[str, str]]]:
    ui_dir = ui_dir.resolve()
    fingerprints: dict[str, str] = {}
    names: dict[str, tuple[str, ...]] = {}
    types: dict[str, dict[str, str]] = {}
    anchor = ui_dir
    for filename in root_filenames:
        root_path = (ui_dir / filename).resolve()
        if not root_path.is_file():
            raise UiXmlIndexError(f"Root UI XML not found: {root_path}")
        fingerprints[filename] = fingerprint_root_xml(root_path, anchor)
        names[filename] = collect_widget_names(root_path, anchor)
        types[filename] = collect_widget_types(root_path, anchor)
    return fingerprints, names, types


def _fingerprints_match(
    meta: dict[str, object],
    current: dict[str, str],
    root_filenames: tuple[str, ...],
) -> bool:
    if meta.get("root_filenames") != list(root_filenames):
        return False
    stored = meta.get("roots")
    if not isinstance(stored, dict):
        return False
    for filename in root_filenames:
        if stored.get(filename) != current.get(filename):
            return False
    return True


def _ensure_generated(out_dir: Path, ui_dir: Path) -> None:
    meta_path = _package_dir() / _META_BASENAME
    root_filenames = _discover_root_filenames(ui_dir)
    fingerprints, names, types = _collect_all(ui_dir, root_filenames)
    meta = _read_meta(meta_path)
    if (
        meta is not None
        and _fingerprints_match(meta, fingerprints, root_filenames)
        and all((out_dir / f"{module_name_from_root_filename(filename)}.py").is_file() for filename in root_filenames)
    ):
        return
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sources = build_module_sources(
        root_filenames=root_filenames,
        per_root_names=names,
        per_root_types=types,
        per_root_fingerprints=fingerprints,
        generated_at=generated_at,
    )
    stored_roots = meta.get("roots") if isinstance(meta, dict) else {}
    for filename in root_filenames:
        rel_path = f"{module_name_from_root_filename(filename)}.py"
        target = out_dir / rel_path
        if (
            isinstance(stored_roots, dict)
            and stored_roots.get(filename) == fingerprints.get(filename)
            and target.is_file()
        ):
            continue
        source = sources[rel_path]
        try:
            _atomic_write_text(target, source)
        except PermissionError:
            if not target.is_file():
                raise
    _atomic_write_json(
        meta_path,
        {
            "version": _META_VERSION,
            "generator_version": GENERATOR_VERSION,
            "generated_at": generated_at,
            "root_filenames": list(root_filenames),
            "roots": fingerprints,
        },
    )


def ensure_ui_key_modules() -> None:
    out_dir = _target_package_dir()
    _assert_writable(out_dir)
    _ensure_generated(out_dir, ui_anchor_dir(_package_dir()))


ensure_ui_key_modules()

__all__ = ("ensure_ui_key_modules",)
