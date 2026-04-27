from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from edid.edid_data import DisplayData, load_display_data
from edid.logging_utils import log_notice


@dataclass(frozen=True)
class EdidLibraryEntry:
    id: str
    name: str
    file_name: str
    type_name: str
    size: int
    product_id: str | None
    display_name: str | None
    source_path: str | None
    created_at: str
    updated_at: str
    content_hash: str = ""
    source_kind: str = "file"
    display_key: str | None = None
    device_id: str | None = None
    instance_id: str | None = None
    source_label: str | None = None
    snapshot_at: str | None = None
    auto_snapshot: bool = False


class EdidLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_library_root()
        self._items_dir = self.root / "items"
        self._manifest_path = self.root / "manifest.json"

    def list_entries(self) -> list[EdidLibraryEntry]:
        entries = self._read_entries()
        return sorted(entries, key=lambda entry: (entry.name.casefold(), entry.updated_at, entry.id))

    def import_file(self, path: str | Path, *, name: str | None = None) -> EdidLibraryEntry:
        source = Path(path)
        data = load_display_data(source, trim=False)
        return self.save_new(data, name=name or _entry_name(data, source.stem), source_path=str(source), source_kind="file")

    def save_new(
        self,
        data: DisplayData,
        *,
        name: str | None = None,
        source_path: str | None = None,
        source_kind: str = "created",
        display_key: str | None = None,
        device_id: str | None = None,
        instance_id: str | None = None,
        source_label: str | None = None,
        auto_snapshot: bool = False,
    ) -> EdidLibraryEntry:
        item_id = uuid4().hex
        file_name = f"{item_id}.bin"
        now = _timestamp()
        entry = EdidLibraryEntry(
            id=item_id,
            name=_clean_name(name or _entry_name(data, "Untitled EDID")),
            file_name=file_name,
            type_name=data.type_name,
            size=data.size,
            product_id=data.product_id(),
            display_name=data.name(),
            source_path=source_path,
            created_at=now,
            updated_at=now,
            content_hash=content_hash(data),
            source_kind=source_kind,
            display_key=display_key,
            device_id=device_id,
            instance_id=instance_id,
            source_label=source_label,
            snapshot_at=now if auto_snapshot else None,
            auto_snapshot=auto_snapshot,
        )
        self._write_data_file(entry, data)
        self._write_entries([*self._read_entries(), entry])
        return entry

    def upsert_snapshot(
        self,
        data: DisplayData,
        *,
        source_kind: str,
        display_key: str,
        device_id: str,
        instance_id: str,
        source_label: str,
        name: str | None = None,
    ) -> EdidLibraryEntry:
        entries = self._read_entries()
        digest = content_hash(data)
        now = _timestamp()
        for index, entry in enumerate(entries):
            if not entry.auto_snapshot:
                continue
            if entry.source_kind != source_kind or entry.display_key != display_key:
                continue
            updated_entry = EdidLibraryEntry(
                id=entry.id,
                name=_clean_name(name or entry.name or source_label),
                file_name=entry.file_name,
                type_name=data.type_name,
                size=data.size,
                product_id=data.product_id(),
                display_name=data.name(),
                source_path=entry.source_path,
                created_at=entry.created_at,
                updated_at=now if entry.content_hash != digest else entry.updated_at,
                content_hash=digest,
                source_kind=source_kind,
                display_key=display_key,
                device_id=device_id,
                instance_id=instance_id,
                source_label=source_label,
                snapshot_at=now,
                auto_snapshot=True,
            )
            if entry.content_hash != digest:
                self._write_data_file(updated_entry, data)
            entries[index] = updated_entry
            self._write_entries(entries)
            return updated_entry
        return self.save_new(
            data,
            name=name or _entry_name(data, source_label),
            source_kind=source_kind,
            display_key=display_key,
            device_id=device_id,
            instance_id=instance_id,
            source_label=source_label,
            auto_snapshot=True,
        )

    def load(self, entry_id: str) -> DisplayData:
        entry = self.get(entry_id)
        return DisplayData(self._data_path(entry).read_bytes())

    def get(self, entry_id: str) -> EdidLibraryEntry:
        for entry in self._read_entries():
            if entry.id == entry_id:
                return entry
        raise KeyError(f"EDID library entry not found: {entry_id}")

    def update_data(self, entry_id: str, data: DisplayData, *, name: str | None = None) -> EdidLibraryEntry:
        entries = self._read_entries()
        updated_entry: EdidLibraryEntry | None = None
        for index, entry in enumerate(entries):
            if entry.id != entry_id:
                continue
            updated_entry = EdidLibraryEntry(
                id=entry.id,
                name=_clean_name(name or entry.name),
                file_name=entry.file_name,
                type_name=data.type_name,
                size=data.size,
                product_id=data.product_id(),
                display_name=data.name(),
                source_path=entry.source_path,
                created_at=entry.created_at,
                updated_at=_timestamp(),
                content_hash=content_hash(data),
                source_kind=entry.source_kind,
                display_key=entry.display_key,
                device_id=entry.device_id,
                instance_id=entry.instance_id,
                source_label=entry.source_label,
                snapshot_at=entry.snapshot_at,
                auto_snapshot=entry.auto_snapshot,
            )
            self._write_data_file(updated_entry, data)
            entries[index] = updated_entry
            break
        if updated_entry is None:
            raise KeyError(f"EDID library entry not found: {entry_id}")
        self._write_entries(entries)
        return updated_entry

    def rename(self, entry_id: str, name: str) -> EdidLibraryEntry:
        entry = self.get(entry_id)
        return self.update_data(entry_id, self.load(entry_id), name=name or entry.name)

    def duplicate(self, entry_id: str, *, name: str | None = None) -> EdidLibraryEntry:
        entry = self.get(entry_id)
        data = self.load(entry_id)
        return self.save_new(
            data,
            name=name or f"{entry.name} Copy",
            source_path=entry.source_path,
            source_kind=entry.source_kind if not entry.auto_snapshot else "created",
            source_label=entry.source_label,
        )

    def delete(self, entry_id: str) -> None:
        entries = self._read_entries()
        kept_entries = [entry for entry in entries if entry.id != entry_id]
        if len(kept_entries) == len(entries):
            raise KeyError(f"EDID library entry not found: {entry_id}")
        for entry in entries:
            if entry.id == entry_id:
                try:
                    self._data_path(entry).unlink(missing_ok=True)
                except PermissionError as exc:
                    log_notice("Library data file could not be deleted; removing manifest entry only", path=self._data_path(entry), error=exc)
                break
        self._write_entries(kept_entries)

    def _read_entries(self) -> list[EdidLibraryEntry]:
        if not self._manifest_path.exists():
            return []
        payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        return [_entry_from_manifest(entry) for entry in entries]

    def _write_entries(self, entries: list[EdidLibraryEntry]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._items_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": [asdict(entry) for entry in entries]}
        self._manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_data_file(self, entry: EdidLibraryEntry, data: DisplayData) -> None:
        self._items_dir.mkdir(parents=True, exist_ok=True)
        self._data_path(entry).write_bytes(data.data)

    def _data_path(self, entry: EdidLibraryEntry) -> Path:
        return self._items_dir / entry.file_name


def _default_library_root() -> Path:
    root = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "ColorlightEdidTools" / "edids"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def content_hash(data: DisplayData) -> str:
    return hashlib.sha256(data.data).hexdigest()


def _entry_from_manifest(entry: dict[str, object]) -> EdidLibraryEntry:
    values = dict(entry)
    values.setdefault("content_hash", "")
    values.setdefault("source_kind", "file" if values.get("source_path") else "created")
    values.setdefault("display_key", None)
    values.setdefault("device_id", None)
    values.setdefault("instance_id", None)
    values.setdefault("source_label", None)
    values.setdefault("snapshot_at", None)
    values.setdefault("auto_snapshot", False)
    return EdidLibraryEntry(**values)


def _entry_name(data: DisplayData, fallback: str) -> str:
    return _clean_name(data.name() or data.product_id() or fallback)


def _clean_name(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text or "Untitled EDID"
