from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os
from typing import Any

from .edid_data import DisplayData, DisplayDataError
from .logging_utils import log_event, log_exception, log_notice


try:
    import winreg
except ImportError:  # pragma: no cover - exercised on non-Windows platforms.
    winreg = None  # type: ignore[assignment]


ENUM_DISPLAY = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
CONTROL_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
CONTROL_GRAPHICS = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
MAX_OVERRIDE_BLOCKS = 4


INTEL_DEFAULT_FAKE_EDID = bytes(
    [
        0x00,
        0xFF,
        0xFF,
        0xFF,
        0xFF,
        0xFF,
        0xFF,
        0x00,
        0x0D,
        0xAF,
        0x23,
        0x17,
        0x00,
        0x00,
        0x00,
        0x00,
        0x02,
        0x15,
        0x01,
        0x04,
        0x95,
        0x26,
        0x15,
        0x78,
        0x02,
        0xD1,
        0xF5,
        0x93,
        0x5D,
        0x59,
        0x90,
        0x26,
        0x1D,
        0x50,
        0x54,
        0x00,
        0x00,
        0x00,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x1D,
        0x36,
        0x80,
        0xA0,
        0x70,
        0x38,
        0x1E,
        0x40,
        0x2E,
        0x1E,
        0x24,
        0x00,
        0x7E,
        0xD7,
        0x10,
        0x00,
        0x00,
        0x18,
        0x00,
        0x00,
        0x00,
        0x05,
        0x00,
        0x74,
        0x8B,
        0x80,
        0x50,
        0x70,
        0x38,
        0x97,
        0x41,
        0x08,
        0x40,
        0x06,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0xFE,
        0x00,
        0x43,
        0x4D,
        0x49,
        0x0A,
        0x20,
        0x20,
        0x20,
        0x20,
        0x20,
        0x20,
        0x20,
        0x20,
        0x20,
        0x00,
        0x00,
        0x00,
        0xFE,
        0x00,
        0x4E,
        0x31,
        0x37,
        0x33,
        0x48,
        0x48,
        0x46,
        0x2D,
        0x45,
        0x32,
        0x31,
        0x20,
        0x20,
        0x00,
        0x39,
    ]
)


class WindowsDisplayError(RuntimeError):
    """Raised for Windows display registry or driver-control failures."""


@dataclass
class DisplayInstance:
    device_id: str
    instance_id: str
    device_desc: str | None
    active_data: DisplayData | None
    override_data: DisplayData | None

    @property
    def key(self) -> str:
        return f"{self.device_id}\\{self.instance_id}"

    @property
    def name(self) -> str:
        if self.override_data and self.override_data.name():
            return self.override_data.name() or "Unknown Display"
        if self.active_data and self.active_data.name():
            return self.active_data.name() or "Unknown Display"
        return _clean_device_desc(self.device_desc) or "Unknown Display"

    @property
    def product_id(self) -> str | None:
        if self.override_data and self.override_data.product_id():
            return self.override_data.product_id()
        if self.active_data and self.active_data.product_id():
            return self.active_data.product_id()
        return self.device_id

    @property
    def has_override(self) -> bool:
        return self.override_data is not None

    @property
    def has_active_edid(self) -> bool:
        return self.active_data is not None

    def label(self) -> str:
        status: list[str] = []
        if self.has_active_edid:
            status.append("active")
        if self.has_override:
            status.append("override")
        status_text = f" ({', '.join(status)})" if status else ""
        product_id = self.product_id or self.device_id
        return f"{self.key} - {product_id} - {self.name}{status_text}"


def require_windows() -> None:
    if os.name != "nt" or winreg is None:
        raise WindowsDisplayError("Windows registry display operations are only available on Windows.")


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError as exc:
        log_exception("Windows admin check failed", exc)
        return False


def list_display_instances(max_blocks: int = MAX_OVERRIDE_BLOCKS) -> list[DisplayInstance]:
    require_windows()
    displays: list[DisplayInstance] = []
    try:
        with _open_hklm(ENUM_DISPLAY, _read_access()) as root:
            for device_id in _enum_subkeys(root):
                with _open_hklm(fr"{ENUM_DISPLAY}\{device_id}", _read_access()) as device_key:
                    for instance_id in _enum_subkeys(device_key):
                        displays.append(_load_instance(device_id, instance_id, max_blocks=max_blocks))
    except FileNotFoundError as exc:
        log_notice("Display registry root not found", path=ENUM_DISPLAY, error=exc)
        return []
    return sorted(displays, key=lambda item: (not item.has_active_edid, item.device_id.upper(), item.instance_id.upper()))


def find_display_instances(target: str | None, *, default_product_id: str | None = None) -> list[DisplayInstance]:
    target = target or default_product_id
    displays = list_display_instances()
    if not target or target.lower() in {"all", "*"}:
        return displays
    normalized = _normalize_target(target)
    matches = [display for display in displays if _matches_target(display, normalized)]
    return matches


def install_edid_override(
    display_data: DisplayData,
    *,
    target: str | None = None,
    allow_invalid: bool = False,
    dry_run: bool = False,
    max_blocks: int = MAX_OVERRIDE_BLOCKS,
) -> list[DisplayInstance]:
    require_windows()
    if not display_data.is_edid:
        raise DisplayDataError("Only EDID data can be installed as a Windows override.")
    if not allow_invalid and not display_data.has_valid_edid_checksums():
        raise DisplayDataError("EDID checksum is invalid. Re-run with --fix or --allow-invalid.")

    blocks = display_data.edid_blocks(max_blocks=max_blocks)
    matches = find_display_instances(target, default_product_id=display_data.product_id())
    if not matches:
        product = display_data.product_id() or "unknown"
        raise WindowsDisplayError(f"No matching display instances found for {target or product}.")

    if dry_run:
        return matches

    for display in matches:
        override_path = fr"{ENUM_DISPLAY}\{display.device_id}\{display.instance_id}\Device Parameters\EDID_OVERRIDE"
        with _create_hklm(override_path, _write_access()) as key:
            for index in range(max_blocks):
                name = str(index)
                if index < len(blocks) and (index == 0 or blocks[index][0] != 0):
                    winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, blocks[index])
                else:
                    _delete_value(key, name)
    return matches


def export_display_data(target: str, *, source: str = "active") -> DisplayData:
    matches = find_display_instances(target)
    if not matches:
        raise WindowsDisplayError(f"No display instances matched {target!r}.")
    display = matches[0]
    if source == "override":
        if not display.override_data:
            raise WindowsDisplayError(f"{display.key} has no EDID override data.")
        return display.override_data
    if source == "active":
        if not display.active_data:
            raise WindowsDisplayError(f"{display.key} has no active EDID data.")
        return display.active_data
    raise WindowsDisplayError(f"Unknown export source: {source}")


def reset_display(target: str | None = None, *, dry_run: bool = False) -> list[DisplayInstance]:
    require_windows()
    matches = find_display_instances(target)
    if not matches:
        raise WindowsDisplayError(f"No display instances matched {target or 'all'!r}.")
    if dry_run:
        return matches
    for display in matches:
        params_path = fr"{ENUM_DISPLAY}\{display.device_id}\{display.instance_id}\Device Parameters"
        try:
            with _open_hklm(params_path, _write_access()) as key:
                _delete_tree(key, "EDID_OVERRIDE")
                _delete_value(key, "EDID")
                _delete_tree(key, "EDID_RECOVERY")
        except FileNotFoundError as exc:
            log_notice("Display parameters key not found while resetting display", path=params_path, error=exc)
            continue
    return matches


def delete_display_instance(target: str, *, dry_run: bool = False) -> DisplayInstance:
    require_windows()
    matches = find_display_instances(target)
    if not matches:
        raise WindowsDisplayError(f"No display instances matched {target!r}.")
    if len(matches) > 1:
        exact = [display for display in matches if display.key.upper() == _normalize_target(target)]
        if len(exact) == 1:
            display = exact[0]
        else:
            raise WindowsDisplayError(f"{target!r} matched multiple display instances; use the full DEVICE\\INSTANCE key.")
    else:
        display = matches[0]
    if dry_run:
        return display
    device_path = fr"{ENUM_DISPLAY}\{display.device_id}"
    full_path = fr"{device_path}\{display.instance_id}"
    try:
        with _open_hklm(device_path, _read_access() | _write_access()) as device_key:
            if not _delete_tree(device_key, display.instance_id):
                raise WindowsDisplayError(f"Failed to delete display instance {display.key}. Registry path: HKLM\\{full_path}")
    except PermissionError as exc:
        diagnostic = diagnose_display_instance_permissions(display)
        raise WindowsDisplayError(
            f"Access denied while deleting monitor registry key.\n"
            f"Registry path: HKLM\\{full_path}\n"
            f"Administrator: {is_admin()}\n\n"
            f"{diagnostic}"
        ) from exc
    except OSError as exc:
        raise WindowsDisplayError(
            f"Failed to delete monitor registry key: {exc}\n"
            f"Registry path: HKLM\\{full_path}\n"
            f"Administrator: {is_admin()}"
        ) from exc
    return display


def diagnose_display_instance_permissions(display: DisplayInstance) -> str:
    full_path = fr"{ENUM_DISPLAY}\{display.device_id}\{display.instance_id}"
    lines = [
        "Permission diagnostic:",
        f"- Instance path: HKLM\\{full_path}",
        f"- Parent path: HKLM\\{ENUM_DISPLAY}\\{display.device_id}",
    ]
    for label, path in (("parent", fr"{ENUM_DISPLAY}\{display.device_id}"), ("instance", full_path)):
        for access_name, access in (
            ("KEY_READ", _read_access()),
            ("KEY_WRITE", winreg.KEY_WRITE if winreg else 0),
            ("DELETE", 0x00010000),
            ("KEY_READ|KEY_WRITE|DELETE", _read_access() | (winreg.KEY_WRITE if winreg else 0) | 0x00010000),
        ):
            try:
                with _open_hklm(path, access):
                    lines.append(f"- {label} open {access_name}: OK")
            except PermissionError as exc:
                lines.append(f"- {label} open {access_name}: ACCESS DENIED ({exc})")
            except OSError as exc:
                lines.append(f"- {label} open {access_name}: ERROR ({exc})")
    lines.append(
        "Likely cause: HKLM\\SYSTEM\\CurrentControlSet\\Enum keys are protected by Plug and Play security descriptors. "
        "Administrators can often edit values below Device Parameters, but deleting the hardware instance key may require SYSTEM/TrustedInstaller ownership or device-manager removal semantics."
    )
    return "\n".join(lines)


def reset_all(*, dry_run: bool = False) -> dict[str, int]:
    require_windows()
    summary = {"graphics_configuration": 0, "graphics_connectivity": 0, "display_instances": 0, "intel_adapters": 0}
    if dry_run:
        summary["display_instances"] = len(list_display_instances())
        return summary

    summary["graphics_configuration"] = _delete_all_subkeys(fr"{CONTROL_GRAPHICS}\Configuration")
    summary["graphics_connectivity"] = _delete_all_subkeys(fr"{CONTROL_GRAPHICS}\Connectivity")
    summary["display_instances"] = len(reset_display("all"))
    summary["intel_adapters"] = _reset_intel_fake_edid()
    return summary


def restart_display_driver() -> tuple[int, int]:
    require_windows()
    disabled = _set_display_driver_state(2)
    enabled = _set_display_driver_state(1)
    if disabled == 0 or enabled == 0:
        raise WindowsDisplayError("Failed to restart the display driver.")
    return disabled, enabled


def restart_display_driver_recovery() -> dict[str, int]:
    """Mirror restart.exe recovery mode: stage EDID recovery, restart, then restore."""
    require_windows()
    staged = begin_recovery_mode()
    disabled = 0
    enabled = 0
    try:
        disabled, enabled = restart_display_driver()
    finally:
        restored = restore_recovery_mode()
    return {
        "staged_displays": staged["display_instances"],
        "staged_intel_adapters": staged["intel_adapters"],
        "disabled_adapters": disabled,
        "enabled_adapters": enabled,
        "restored_displays": restored["display_instances"],
        "restored_intel_adapters": restored["intel_adapters"],
    }


def restart_display_driver_quiet(*, recovery: bool = False) -> dict[str, int]:
    if recovery:
        return restart_display_driver_recovery()
    disabled, enabled = restart_display_driver()
    return {"disabled_adapters": disabled, "enabled_adapters": enabled}


def begin_recovery_mode() -> dict[str, int]:
    require_windows()
    moved_displays = _move_display_override_keys("EDID_OVERRIDE", "EDID_RECOVERY")
    moved_intel = _stage_intel_fake_edid_recovery()
    return {"display_instances": moved_displays, "intel_adapters": moved_intel}


def restore_recovery_mode() -> dict[str, int]:
    require_windows()
    restored_displays = _move_display_override_keys("EDID_RECOVERY", "EDID_OVERRIDE")
    restored_intel = _restore_intel_fake_edid_recovery()
    return {"display_instances": restored_displays, "intel_adapters": restored_intel}


def _load_instance(device_id: str, instance_id: str, *, max_blocks: int) -> DisplayInstance:
    instance_path = fr"{ENUM_DISPLAY}\{device_id}\{instance_id}"
    params_path = fr"{instance_path}\Device Parameters"
    device_desc: str | None = None
    active_data: DisplayData | None = None
    override_data: DisplayData | None = None

    try:
        with _open_hklm(instance_path, _read_access()) as key:
            device_desc = _query_value(key, "DeviceDesc")
    except FileNotFoundError as exc:
        log_notice("Display instance key not found while loading", path=instance_path, error=exc)
        pass

    try:
        with _open_hklm(params_path, _read_access()) as key:
            active = _query_value(key, "EDID")
            if isinstance(active, bytes) and len(active) >= 128:
                active_data = DisplayData(active).trim_to_reported_size(max_size=max_blocks * 128)
    except FileNotFoundError as exc:
        log_notice("Display has no Device Parameters key while loading active EDID", path=params_path, error=exc)
        pass

    try:
        with _open_hklm(fr"{params_path}\EDID_OVERRIDE", _read_access()) as key:
            blocks: dict[int, bytes] = {}
            for index in range(max_blocks):
                value = _query_value(key, str(index))
                if isinstance(value, bytes) and len(value) >= 128:
                    blocks[index] = value[:128]
            if 0 in blocks:
                highest = max(blocks)
                raw = b"".join(blocks.get(index, bytes(128)) for index in range(highest + 1))
                override_data = DisplayData(raw).trim_to_reported_size(max_size=max_blocks * 128)
    except FileNotFoundError as exc:
        log_notice("Display has no EDID override key", path=fr"{params_path}\EDID_OVERRIDE", error=exc)
        pass

    return DisplayInstance(device_id, instance_id, device_desc, active_data, override_data)


def _matches_target(display: DisplayInstance, normalized_target: str) -> bool:
    candidates = {
        _normalize_target(display.device_id),
        _normalize_target(display.key),
        _normalize_target(display.instance_id),
    }
    if display.product_id:
        candidates.add(_normalize_target(display.product_id))
    if display.active_data and display.active_data.product_id():
        candidates.add(_normalize_target(display.active_data.product_id() or ""))
    if display.override_data and display.override_data.product_id():
        candidates.add(_normalize_target(display.override_data.product_id() or ""))
    return normalized_target in candidates


def _normalize_target(value: str) -> str:
    return value.strip().replace("/", "\\").upper()


def _clean_device_desc(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(";", 1)[-1]


def _query_value(key: Any, name: str) -> Any:
    try:
        value, _value_type = winreg.QueryValueEx(key, name)
        return value
    except FileNotFoundError as exc:
        log_notice("Registry value not found", name=name, error=exc)
        return None


def _enum_subkeys(key: Any) -> list[str]:
    items: list[str] = []
    index = 0
    while True:
        try:
            items.append(winreg.EnumKey(key, index))
        except OSError:
            return items
        index += 1


def _enum_values(key: Any) -> list[str]:
    items: list[str] = []
    index = 0
    while True:
        try:
            name, _value, _value_type = winreg.EnumValue(key, index)
            items.append(name)
        except OSError:
            return items
        index += 1


def _open_hklm(path: str, access: int) -> Any:
    return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, access | _key_64())


def _create_hklm(path: str, access: int) -> Any:
    return winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, access | _key_64())


def _read_access() -> int:
    return winreg.KEY_READ


def _write_access() -> int:
    return winreg.KEY_READ | winreg.KEY_WRITE | 0x00010000


def _key_64() -> int:
    return getattr(winreg, "KEY_WOW64_64KEY", 0)


def _delete_value(key: Any, name: str) -> bool:
    try:
        winreg.DeleteValue(key, name)
        return True
    except FileNotFoundError as exc:
        log_notice("Registry value delete skipped; value not found", name=name, error=exc)
        return False


def _delete_tree(key: Any, subkey: str) -> bool:
    try:
        if hasattr(winreg, "DeleteTree"):
            winreg.DeleteTree(key, subkey)
        else:
            _delete_tree_recursive(key, subkey)
        return True
    except FileNotFoundError as exc:
        log_notice("Registry tree delete skipped; subkey not found", subkey=subkey, error=exc)
        return False


def _delete_tree_recursive(parent: Any, subkey: str) -> None:
    with winreg.OpenKey(parent, subkey, 0, _read_access() | _write_access() | _key_64()) as child:
        for child_name in _enum_subkeys(child):
            _delete_tree_recursive(child, child_name)
    winreg.DeleteKey(parent, subkey)


def _delete_all_subkeys(path: str) -> int:
    try:
        with _open_hklm(path, _read_access() | _write_access()) as key:
            deleted = 0
            for name in list(_enum_subkeys(key)):
                if _delete_tree(key, name):
                    deleted += 1
            return deleted
    except FileNotFoundError as exc:
        log_exception("Registry subtree root not found while deleting all subkeys", exc, path=path)
        return 0


def _copy_key_values(source: Any, target: Any, *, clear_target: bool = False) -> int:
    copied = 0
    if clear_target:
        for name in list(_enum_values(target)):
            _delete_value(target, name)
    for name in _enum_values(source):
        value, value_type = winreg.QueryValueEx(source, name)
        winreg.SetValueEx(target, name, 0, value_type, value)
        copied += 1
    return copied


def _move_display_override_keys(source_name: str, target_name: str) -> int:
    moved = 0
    for display in list_display_instances():
        params_path = fr"{ENUM_DISPLAY}\{display.device_id}\{display.instance_id}\Device Parameters"
        try:
            with _open_hklm(params_path, _write_access()) as params_key:
                try:
                    with winreg.OpenKey(params_key, source_name, 0, _read_access() | _key_64()) as source_key:
                        with winreg.CreateKeyEx(params_key, target_name, 0, _write_access() | _key_64()) as target_key:
                            copied = _copy_key_values(source_key, target_key, clear_target=True)
                    _delete_tree(params_key, source_name)
                    if copied > 0:
                        moved += 1
                except FileNotFoundError as exc:
                    log_notice("Display override/recovery key missing during move", path=params_path, source=source_name, target=target_name, error=exc)
                    continue
        except FileNotFoundError as exc:
            log_notice("Display parameters key missing during override/recovery move", path=params_path, error=exc)
            continue
    return moved


def _stage_intel_fake_edid_recovery() -> int:
    staged = 0
    try:
        with _open_hklm(CONTROL_CLASS, _read_access()) as root:
            adapters = _enum_subkeys(root)
    except FileNotFoundError as exc:
        log_notice("Control class registry key not found while staging Intel recovery", path=CONTROL_CLASS, error=exc)
        return 0

    for adapter in adapters:
        if len(adapter) != 4:
            continue
        path = fr"{CONTROL_CLASS}\{adapter}"
        try:
            with _open_hklm(path, _read_access() | _write_access()) as key:
                provider = _query_value(key, "ProviderName")
                if not isinstance(provider, str) or not provider.lower().startswith("intel"):
                    continue

                with winreg.CreateKeyEx(key, "EDID_RECOVERY", 0, _write_access() | _key_64()) as recovery_key:
                    for value in list(_enum_values(key)):
                        if value.startswith("FakeEDID_") or value == "ReadEDIDFromRegistry":
                            value_data, value_type = winreg.QueryValueEx(key, value)
                            winreg.SetValueEx(recovery_key, value, 0, value_type, value_data)
                            _delete_value(key, value)

                winreg.SetValueEx(key, "FakeEDID_14_0_af0d_1723", 0, winreg.REG_BINARY, INTEL_DEFAULT_FAKE_EDID)
                winreg.SetValueEx(key, "ReadEDIDFromRegistry", 0, winreg.REG_DWORD, 1)
                staged += 1
        except FileNotFoundError as exc:
            log_notice("Intel adapter registry key missing during recovery staging", path=path, error=exc)
            continue
    return staged


def _restore_intel_fake_edid_recovery() -> int:
    restored = 0
    try:
        with _open_hklm(CONTROL_CLASS, _read_access()) as root:
            adapters = _enum_subkeys(root)
    except FileNotFoundError as exc:
        log_notice("Control class registry key not found while restoring Intel recovery", path=CONTROL_CLASS, error=exc)
        return 0

    for adapter in adapters:
        if len(adapter) != 4:
            continue
        path = fr"{CONTROL_CLASS}\{adapter}"
        try:
            with _open_hklm(path, _read_access() | _write_access()) as key:
                provider = _query_value(key, "ProviderName")
                if not isinstance(provider, str) or not provider.lower().startswith("intel"):
                    continue

                try:
                    with winreg.OpenKey(key, "EDID_RECOVERY", 0, _read_access() | _key_64()) as recovery_key:
                        for value in list(_enum_values(key)):
                            if value.startswith("FakeEDID_") or value == "ReadEDIDFromRegistry":
                                _delete_value(key, value)
                        _copy_key_values(recovery_key, key, clear_target=False)
                    _delete_tree(key, "EDID_RECOVERY")
                    restored += 1
                except FileNotFoundError as exc:
                    log_notice("Intel EDID_RECOVERY key missing during restore", path=path, error=exc)
                    continue
        except FileNotFoundError as exc:
            log_notice("Intel adapter registry key missing during recovery restore", path=path, error=exc)
            continue
    return restored


def _reset_intel_fake_edid() -> int:
    count = 0
    try:
        with _open_hklm(CONTROL_CLASS, _read_access()) as root:
            adapters = _enum_subkeys(root)
    except FileNotFoundError as exc:
        log_notice("Control class registry key not found while resetting Intel fake EDID", path=CONTROL_CLASS, error=exc)
        return 0

    for adapter in adapters:
        if len(adapter) != 4:
            continue
        path = fr"{CONTROL_CLASS}\{adapter}"
        try:
            with _open_hklm(path, _read_access() | _write_access()) as key:
                provider = _query_value(key, "ProviderName")
                if not isinstance(provider, str) or not provider.lower().startswith("intel"):
                    continue
                for value in list(_enum_values(key)):
                    if value.startswith("FakeEDID_") and value != "FakeEDID_14_0_af0d_1723":
                        _delete_value(key, value)
                winreg.SetValueEx(key, "FakeEDID_14_0_af0d_1723", 0, winreg.REG_BINARY, INTEL_DEFAULT_FAKE_EDID)
                winreg.SetValueEx(key, "ReadEDIDFromRegistry", 0, winreg.REG_DWORD, 1)
                _delete_tree(key, "EDID_RECOVERY")
                count += 1
        except FileNotFoundError as exc:
            log_notice("Intel adapter registry key missing during fake EDID reset", path=path, error=exc)
            continue
    return count


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", getattr(wintypes, "ULONG_PTR", ctypes.c_size_t)),
    ]


class SP_CLASSINSTALL_HEADER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InstallFunction", wintypes.DWORD)]


class SP_PROPCHANGE_PARAMS(ctypes.Structure):
    _fields_ = [
        ("ClassInstallHeader", SP_CLASSINSTALL_HEADER),
        ("StateChange", wintypes.DWORD),
        ("Scope", wintypes.DWORD),
        ("HwProfile", wintypes.DWORD),
    ]


GUID_DEVCLASS_DISPLAY = GUID(
    0x4D36E968,
    0xE325,
    0x11CE,
    (wintypes.BYTE * 8)(0xBF, 0xC1, 0x08, 0x00, 0x2B, 0xE1, 0x03, 0x18),
)


def _set_display_driver_state(state: int) -> int:
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    setupapi.SetupDiEnumDeviceInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
    setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
    setupapi.SetupDiSetClassInstallParamsW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(SP_DEVINFO_DATA),
        ctypes.POINTER(SP_CLASSINSTALL_HEADER),
        wintypes.DWORD,
    ]
    setupapi.SetupDiSetClassInstallParamsW.restype = wintypes.BOOL
    setupapi.SetupDiCallClassInstaller.argtypes = [wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA)]
    setupapi.SetupDiCallClassInstaller.restype = wintypes.BOOL
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    devices = setupapi.SetupDiGetClassDevsW(ctypes.byref(GUID_DEVCLASS_DISPLAY), None, None, 0x00000002)
    if devices == wintypes.HANDLE(-1).value:
        return 0

    changed = 0
    try:
        index = 0
        while True:
            device = SP_DEVINFO_DATA()
            device.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not setupapi.SetupDiEnumDeviceInfo(devices, index, ctypes.byref(device)):
                break
            params = SP_PROPCHANGE_PARAMS()
            params.ClassInstallHeader.cbSize = ctypes.sizeof(SP_CLASSINSTALL_HEADER)
            params.ClassInstallHeader.InstallFunction = 0x00000012
            params.StateChange = state
            params.Scope = 0x00000001
            params.HwProfile = 0
            header = ctypes.byref(params.ClassInstallHeader)
            if setupapi.SetupDiSetClassInstallParamsW(devices, ctypes.byref(device), header, ctypes.sizeof(params)):
                if setupapi.SetupDiCallClassInstaller(0x00000012, devices, ctypes.byref(device)):
                    changed += 1
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(devices)
    return changed
