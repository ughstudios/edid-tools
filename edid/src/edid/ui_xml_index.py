"""XML UI index: transitive includes, path guard, widget name discovery (no PySide6)."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
import shutil


class UiXmlIndexError(RuntimeError):
    """Raised when XML UI indexing fails."""


def ui_anchor_dir(package_dir: Path) -> Path:
    """Directory containing root XML files (…/edid/xml)."""
    anchor = (package_dir.parents[1] / "xml").resolve()
    _seed_xml_assets(anchor, package_dir / "ui")
    return anchor


def _seed_xml_assets(target_dir: Path, legacy_dir: Path) -> None:
    if not legacy_dir.is_dir():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in legacy_dir.glob("*.xml"):
        destination = target_dir / source.name
        if destination.is_file():
            continue
        shutil.copy2(source, destination)


def resolve_include_target(include_el: ET.Element, base_dir: Path, ui_anchor: Path) -> Path:
    """Resolve <include file=…> like ui_factory._load_include; must stay under ui_anchor."""
    file_name = include_el.attrib.get("file")
    if not file_name:
        raise UiXmlIndexError("include requires a file attribute.")
    candidate = (base_dir / file_name).resolve()
    anchor = ui_anchor.resolve()
    try:
        candidate.relative_to(anchor)
    except ValueError as exc:
        raise UiXmlIndexError(f"Include path escapes UI directory: {candidate}") from exc
    if not candidate.is_file():
        raise UiXmlIndexError(f"Included XML not found: {candidate}")
    return candidate


def collect_transitive_xml_paths(root_xml: Path, ui_anchor: Path) -> frozenset[Path]:
    """All XML files reachable from root_xml via includes (same base_dir rules as ui_factory)."""
    root_xml = root_xml.resolve()
    found: set[Path] = {root_xml}

    def walk(element: ET.Element, base_dir: Path) -> None:
        if element.tag == "include":
            path = resolve_include_target(element, base_dir, ui_anchor)
            found.add(path)
            inner = ET.parse(path).getroot()
            walk(inner, path.parent)
            return
        for child in element:
            walk(child, base_dir)

    walk(ET.parse(root_xml).getroot(), root_xml.parent)
    return frozenset(found)


def fingerprint_root_xml(root_xml: Path, ui_anchor: Path) -> str:
    """SHA256 over sorted relative path + NUL + raw bytes per file (streaming)."""
    anchor = ui_anchor.resolve()
    paths = sorted(collect_transitive_xml_paths(root_xml, ui_anchor), key=lambda p: p.relative_to(anchor).as_posix())
    hasher = hashlib.sha256()
    for path in paths:
        rel = path.relative_to(anchor).as_posix().encode("utf-8")
        hasher.update(rel)
        hasher.update(b"\0")
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)
    return hasher.hexdigest()


def collect_widget_names(root_xml: Path, ui_anchor: Path) -> tuple[str, ...]:
    """
    Pre-order traversal of the logical tree (includes expanded).
    Every element with a name= attribute is registered by ui_factory._register when built.
    """
    root_xml = root_xml.resolve()
    seen: set[str] = set()

    def walk(element: ET.Element, base_dir: Path) -> None:
        if element.tag == "include":
            path = resolve_include_target(element, base_dir, ui_anchor)
            inner = ET.parse(path).getroot()
            walk(inner, path.parent)
            return
        name = element.attrib.get("name")
        if name:
            if name in seen:
                raise UiXmlIndexError(f"Duplicate widget name {name!r} in {root_xml.name}")
            seen.add(name)
        for child in element:
            walk(child, base_dir)

    walk(ET.parse(root_xml).getroot(), root_xml.parent)
    return tuple(sorted(seen))


def collect_widget_types(root_xml: Path, ui_anchor: Path) -> dict[str, str]:
    """
    Build {name: type_name} for every named node registered by ui_factory.
    Type names are unqualified Qt class names used for typing stubs.
    """
    root_xml = root_xml.resolve()
    seen: dict[str, str] = {}

    def type_name_for(element: ET.Element) -> str:
        tag = element.tag
        if tag == "widget":
            return element.attrib.get("class", "QWidget")
        if tag == "tabs":
            return "QTabWidget"
        if tag == "stack":
            return "QStackedWidget"
        if tag == "splitter":
            return "QSplitter"
        if tag == "menu_bar":
            return "QMenuBar"
        if tag == "menu":
            return "QMenu"
        if tag == "action":
            return "QAction"
        if tag == "tab":
            return "QWidget"
        if tag == "wizard_page":
            return "QWizardPage"
        if tag == "vbox":
            return "QVBoxLayout"
        if tag == "hbox":
            return "QHBoxLayout"
        if tag == "grid":
            return "QGridLayout"
        if tag == "form":
            return "QFormLayout"
        return tag

    def walk(element: ET.Element, base_dir: Path) -> None:
        if element.tag == "include":
            path = resolve_include_target(element, base_dir, ui_anchor)
            inner = ET.parse(path).getroot()
            walk(inner, path.parent)
            return
        name = element.attrib.get("name")
        if name:
            if name in seen:
                raise UiXmlIndexError(f"Duplicate widget name {name!r} in {root_xml.name}")
            seen[name] = type_name_for(element)
        for child in element:
            walk(child, base_dir)

    walk(ET.parse(root_xml).getroot(), root_xml.parent)
    return dict(sorted(seen.items()))
