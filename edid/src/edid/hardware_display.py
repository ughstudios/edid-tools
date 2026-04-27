from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
from enum import IntEnum
import os
import re
import subprocess
import time
from typing import Callable

from edid.edid_data import DisplayData
from edid.logging_utils import log_event, log_exception, log_notice


EDID_I2C_ADDRESS = 0xA0
DISPLAYID_I2C_ADDRESS = 0xA4
READ_SIZE = 256


class HardwareDisplayError(RuntimeError):
    """Raised for AMD ADL / NVIDIA NVAPI DDC failures."""


@dataclass
class HardwareDisplay:
    vendor: str
    gpu_label: str
    output_label: str
    name: str
    product_id: str | None
    _read_i2c: Callable[[int, int], bytes]
    _write_i2c: Callable[[bytes], None]
    edid: DisplayData | None = None

    @property
    def key(self) -> str:
        return f"{self.vendor}:{self.gpu_label}:{self.output_label}"

    def label(self) -> str:
        product = self.product_id or "unknown"
        return f"{self.key} - {product} - {self.name or 'Unknown Display'}"

    def read_edid(self) -> DisplayData:
        data = self._read_data(EDID_I2C_ADDRESS)
        self.edid = data
        return data

    def read_displayid(self) -> DisplayData:
        return self._read_data(DISPLAYID_I2C_ADDRESS)

    def write_edid(self, data: DisplayData, *, fast: bool = True) -> None:
        old = self.edid or self.read_edid()
        self._write_data(EDID_I2C_ADDRESS, old, data, fast=fast)
        self.edid = data

    def write_displayid(self, data: DisplayData, *, fast: bool = True) -> None:
        old = self.read_displayid()
        self._write_data(DISPLAYID_I2C_ADDRESS, old, data, fast=fast)

    def write_and_verify_edid(self, data: DisplayData) -> None:
        old = self.read_edid()
        if old.data == data.data:
            return
        self.write_edid(data, fast=True)
        readback = self.read_edid()
        if readback.data == old.data:
            raise HardwareDisplayError("Display is write-protected.")
        if readback.data != data.data:
            self.write_edid(data, fast=False)
            readback = self.read_edid()
            if readback.data != data.data:
                raise HardwareDisplayError("Failed to verify EDID write.")

    def write_and_verify_displayid(self, data: DisplayData) -> None:
        old = self.read_displayid()
        if old.data == data.data:
            return
        self.write_displayid(data, fast=True)
        readback = self.read_displayid()
        if readback.data == old.data:
            raise HardwareDisplayError("Display is write-protected.")
        if readback.data != data.data:
            self.write_displayid(data, fast=False)
            readback = self.read_displayid()
            if readback.data != data.data:
                raise HardwareDisplayError("Failed to verify DisplayID write.")

    def _read_data(self, address: int) -> DisplayData:
        self._write_i2c(bytes([address, 0x00]))
        time.sleep(0.01)
        return DisplayData(self._read_i2c(address + 1, READ_SIZE)).trim_to_reported_size(max_size=READ_SIZE)

    def _write_data(self, address: int, old_data: DisplayData, new_data: DisplayData, *, fast: bool) -> None:
        old = old_data.data
        new = new_data.data
        if len(new) > READ_SIZE:
            raise HardwareDisplayError(f"Hardware DDC writes are limited to {READ_SIZE} bytes.")
        if fast:
            offsets = range((len(new) - 1) // 8 * 8, -1, -8)
            width = 8
        else:
            offsets = range(len(new) - 1, -1, -1)
            width = 1
        for offset in offsets:
            chunk = new[offset : offset + width]
            if offset < len(old) and old[offset : offset + width] == chunk:
                continue
            command = bytes([address, offset]) + chunk
            for attempt in range(10):
                try:
                    self._write_i2c(command)
                    break
                except HardwareDisplayError as exc:
                    log_exception("Hardware write attempt failed", exc, offset=offset, width=width, attempt=attempt + 1)
                    if attempt == 9:
                        raise
                    time.sleep(0.01)
            time.sleep(0.01)


@dataclass
class HardwareBackendStatus:
    backend: str
    available: bool
    message: str
    display_count: int = 0


@dataclass
class HardwareProbeResult:
    ok: bool
    display: str
    messages: list[str]


def require_windows() -> None:
    if os.name != "nt":
        raise HardwareDisplayError("Windows vendor DDC backend is only available on Windows.")


def list_hardware_displays() -> list[HardwareDisplay]:
    displays: list[HardwareDisplay] = []
    loaders = [_list_amd_displays, _list_nvidia_displays] if os.name == "nt" else [_list_ddcutil_displays]
    for loader in loaders:
        try:
            displays.extend(loader())
        except HardwareDisplayError as exc:
            log_notice("Hardware display loader unavailable", loader=getattr(loader, "__name__", str(loader)), error=exc)
            continue
    unique: dict[str, HardwareDisplay] = {}
    for display in displays:
        unique[display.key] = display
    return sorted(unique.values(), key=lambda item: (item.product_id or "", item.name, item.key))


def hardware_backend_status() -> list[HardwareBackendStatus]:
    if os.name != "nt":
        try:
            displays = _list_ddcutil_displays()
            return [HardwareBackendStatus("Linux ddcutil", True, "available", len(displays))]
        except HardwareDisplayError as exc:
            return [
                HardwareBackendStatus(
                    "Linux ddcutil",
                    False,
                    f"{exc}. Install ddcutil and grant access to /dev/i2c-* to enable hardware EDID reads.",
                    0,
                )
            ]
    statuses: list[HardwareBackendStatus] = []
    for name, loader in (("AMD ADL", _list_amd_displays), ("NVIDIA NVAPI", _list_nvidia_displays)):
        try:
            displays = loader()
            statuses.append(HardwareBackendStatus(name, True, "available", len(displays)))
        except HardwareDisplayError as exc:
            statuses.append(HardwareBackendStatus(name, False, str(exc), 0))
    return statuses


def diagnose_hardware_display(display: HardwareDisplay) -> HardwareProbeResult:
    messages: list[str] = [f"Display: {display.label()}"]
    try:
        data = display.read_edid()
    except HardwareDisplayError as exc:
        messages.append(f"EDID read failed: {exc}")
        messages.append(_diagnose_error_text(str(exc)))
        return HardwareProbeResult(False, display.label(), messages)
    messages.append(f"Read {data.size} byte(s) from EDID EEPROM/DDC path.")
    if data.has_valid_edid_header:
        messages.append("EDID header is valid.")
    elif data.has_corrupted_edid_header:
        messages.append("EDID-like data was returned, but the header is corrupted.")
    else:
        messages.append("Returned data does not look like EDID. The display/driver may block direct EEPROM reads.")
    if data.has_valid_edid_checksums():
        messages.append("EDID checksum is valid.")
    else:
        messages.append("EDID checksum is invalid or incomplete.")
    if display.vendor in {"NVIDIA", "AMD"}:
        messages.append("If this is an HDMI TV, the GPU may expose cached EDID to Windows while blocking raw EEPROM/DDC transactions.")
    return HardwareProbeResult(data.has_valid_edid_header and data.has_valid_edid_checksums(), display.label(), messages)


def _diagnose_error_text(message: str) -> str:
    lowered = message.lower()
    if "nvapi" in lowered or "nvidia" in lowered:
        return "NVIDIA detected the output, but the NVAPI I2C/DDC transaction failed. This often means the sink blocks direct EEPROM access or the driver does not expose DDC for this HDMI path."
    if "adl" in lowered or "amd" in lowered:
        return "AMD ADL detected the output, but the DDC transaction failed. This often means the sink blocks direct EEPROM access or the adapter path does not expose DDC."
    if "write-protected" in lowered:
        return "The display accepted the command path but did not change data, which indicates write protection."
    if "ddcutil" in lowered:
        return "ddcutil could not read EDID from the I2C bus. Check permissions for /dev/i2c-* and whether the display exposes DDC."
    return "Direct EEPROM/DDC access appears blocked or unsupported for this display path. Use the Windows override workflow if you only need Windows to see a different EDID."


def make_mock_hardware_display(initial_data: bytes) -> HardwareDisplay:
    """Create an in-memory DDC display for tests; it never touches hardware."""
    memory = bytearray(initial_data[:READ_SIZE].ljust(READ_SIZE, b"\x00"))
    pointer = {"offset": 0}

    def read_i2c(_address: int, size: int) -> bytes:
        return bytes(memory[pointer["offset"] : pointer["offset"] + size]).ljust(size, b"\x00")

    def write_i2c(data: bytes) -> None:
        if len(data) < 2:
            raise HardwareDisplayError("I2C write command is too short.")
        if data[0] in {EDID_I2C_ADDRESS, DISPLAYID_I2C_ADDRESS} and len(data) == 2:
            pointer["offset"] = data[1]
            return
        pointer["offset"] = data[1]
        memory[pointer["offset"] : pointer["offset"] + len(data[2:])] = data[2:]

    display_data = DisplayData(bytes(memory)).trim_to_reported_size(max_size=READ_SIZE)
    return HardwareDisplay("MOCK", "0", "0", display_data.name() or "Mock Display", display_data.product_id(), read_i2c, write_i2c, display_data)


def _list_ddcutil_displays() -> list[HardwareDisplay]:
    if os.name == "nt":
        return []
    if _run(["ddcutil", "--version"]).returncode != 0:
        raise HardwareDisplayError("ddcutil was not found")
    detect = _run(["ddcutil", "detect", "--brief"])
    if detect.returncode != 0:
        raise HardwareDisplayError(detect.stderr.strip() or "ddcutil detect failed")
    displays: list[HardwareDisplay] = []
    display_number: str | None = None
    i2c_bus = ""
    model = "Unknown Display"
    for line in detect.stdout.splitlines():
        display_match = re.search(r"Display\s+(\d+)", line)
        if display_match:
            if display_number is not None:
                item = _make_ddcutil_display(display_number, i2c_bus, model)
                if item:
                    displays.append(item)
            display_number = display_match.group(1)
            i2c_bus = ""
            model = "Unknown Display"
            continue
        bus_match = re.search(r"I2C bus:\s*(.+)", line)
        if bus_match:
            i2c_bus = bus_match.group(1).strip()
        model_match = re.search(r"Monitor:\s*(.+)", line)
        if model_match:
            model = model_match.group(1).strip()
    if display_number is not None:
        item = _make_ddcutil_display(display_number, i2c_bus, model)
        if item:
            displays.append(item)
    return displays


def _make_ddcutil_display(display_number: str, i2c_bus: str, model: str) -> HardwareDisplay | None:
    def read_i2c(_address: int, _size: int) -> bytes:
        completed = _run(["ddcutil", "get-edid", "--display", display_number, "--bytes-only"])
        if completed.returncode != 0:
            raise HardwareDisplayError(completed.stderr.strip() or "ddcutil get-edid failed")
        tokens = re.findall(r"\b[0-9A-Fa-f]{2}\b", completed.stdout)
        if not tokens:
            raise HardwareDisplayError("ddcutil did not return EDID bytes")
        return bytes(int(token, 16) for token in tokens)

    def write_i2c(_data: bytes) -> None:
        raise HardwareDisplayError("EEPROM writes are not implemented for the ddcutil backend.")

    try:
        edid = DisplayData(read_i2c(EDID_I2C_ADDRESS + 1, READ_SIZE)).trim_to_reported_size(max_size=READ_SIZE)
    except HardwareDisplayError as exc:
        log_notice("ddcutil display initial EDID read failed", display=display_number, bus=i2c_bus, error=exc)
        edid = None
    return HardwareDisplay(
        "DDCUTIL",
        display_number,
        i2c_bus or display_number,
        (edid.name() if edid else None) or model,
        edid.product_id() if edid else None,
        read_i2c,
        write_i2c,
        edid,
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except FileNotFoundError as exc:
        log_exception("External command not found", exc, command=command)
        return subprocess.CompletedProcess(command, 127, "", f"{command[0]} not found")


class AmdAdapterInfo(ctypes.Structure):
    _fields_ = [
        ("iSize", ctypes.c_int),
        ("iAdapterIndex", ctypes.c_int),
        ("strUDID", ctypes.c_char * 256),
        ("iBusNumber", ctypes.c_int),
        ("iDeviceNumber", ctypes.c_int),
        ("iFunctionNumber", ctypes.c_int),
        ("iVendorID", ctypes.c_int),
        ("strAdapterName", ctypes.c_char * 256),
        ("strDisplayName", ctypes.c_char * 256),
        ("iPresent", ctypes.c_int),
        ("iExist", ctypes.c_int),
        ("strDriverPath", ctypes.c_char * 256),
        ("strDriverPathExt", ctypes.c_char * 256),
        ("strPNPString", ctypes.c_char * 256),
        ("iOSDisplayIndex", ctypes.c_int),
    ]


class AmdDisplayID(ctypes.Structure):
    _fields_ = [
        ("iDisplayLogicalIndex", ctypes.c_int),
        ("iDisplayPhysicalIndex", ctypes.c_int),
        ("iDisplayLogicalAdapterIndex", ctypes.c_int),
        ("iDisplayPhysicalAdapterIndex", ctypes.c_int),
    ]


class AmdDisplayInfo(ctypes.Structure):
    _fields_ = [
        ("displayID", AmdDisplayID),
        ("iDisplayControllerIndex", ctypes.c_int),
        ("strDisplayName", ctypes.c_char * 256),
        ("strDisplayManufacturerName", ctypes.c_char * 256),
        ("iDisplayType", ctypes.c_int),
        ("iDisplayOutputType", ctypes.c_int),
        ("iDisplayConnector", ctypes.c_int),
        ("iDisplayInfoMask", ctypes.c_int),
        ("iDisplayInfoValue", ctypes.c_int),
    ]


class AmdLibrary:
    ADL_OK = 0

    def __init__(self) -> None:
        require_windows()
        self._allocations: list[ctypes.Array[ctypes.c_char]] = []
        self._malloc_callback_type = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)
        self._malloc_callback = self._malloc_callback_type(self._malloc)
        self.dll = self._load_library("atiadlxx.dll", "atiadlxy.dll")
        self._bind()
        if self.ADL_Main_Control_Create(self._malloc_callback, 1) != self.ADL_OK:
            raise HardwareDisplayError("ADL_Main_Control_Create failed.")

    def close(self) -> None:
        try:
            self.ADL_Main_Control_Destroy()
        except Exception as exc:
            log_exception("AMD ADL destroy failed", exc)
            pass

    def _malloc(self, size: int) -> int:
        buffer = ctypes.create_string_buffer(size)
        self._allocations.append(buffer)
        return ctypes.addressof(buffer)

    def _load_library(self, *names: str) -> ctypes.WinDLL:
        for name in names:
            try:
                return ctypes.WinDLL(name)
            except OSError as exc:
                log_notice("AMD ADL library load attempt failed", library=name, error=exc)
                continue
        raise HardwareDisplayError("AMD ADL library not found.")

    def _bind(self) -> None:
        self.ADL_Main_Control_Create = self.dll.ADL_Main_Control_Create
        self.ADL_Main_Control_Create.argtypes = [self._malloc_callback_type, ctypes.c_int]
        self.ADL_Main_Control_Create.restype = ctypes.c_int
        self.ADL_Adapter_NumberOfAdapters_Get = self.dll.ADL_Adapter_NumberOfAdapters_Get
        self.ADL_Adapter_NumberOfAdapters_Get.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self.ADL_Adapter_NumberOfAdapters_Get.restype = ctypes.c_int
        self.ADL_Adapter_AdapterInfo_Get = self.dll.ADL_Adapter_AdapterInfo_Get
        self.ADL_Adapter_AdapterInfo_Get.argtypes = [ctypes.POINTER(AmdAdapterInfo), ctypes.c_int]
        self.ADL_Adapter_AdapterInfo_Get.restype = ctypes.c_int
        self.ADL_Display_DisplayInfo_Get = self.dll.ADL_Display_DisplayInfo_Get
        self.ADL_Display_DisplayInfo_Get.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.POINTER(AmdDisplayInfo)),
            ctypes.c_int,
        ]
        self.ADL_Display_DisplayInfo_Get.restype = ctypes.c_int
        self.ADL_Display_DDCBlockAccess_Get = self.dll.ADL_Display_DDCBlockAccess_Get
        self.ADL_Display_DDCBlockAccess_Get.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        self.ADL_Display_DDCBlockAccess_Get.restype = ctypes.c_int
        self.ADL_Main_Control_Destroy = self.dll.ADL_Main_Control_Destroy
        self.ADL_Main_Control_Destroy.argtypes = []
        self.ADL_Main_Control_Destroy.restype = ctypes.c_int

    def read_i2c(self, adapter: int, output: int, address: int, size: int) -> bytes:
        send = (ctypes.c_ubyte * 1)(address)
        recv_size = ctypes.c_int(size)
        buffer = (ctypes.c_ubyte * size)()
        status = self.ADL_Display_DDCBlockAccess_Get(adapter, output, 0, 0, 1, send, ctypes.byref(recv_size), buffer)
        if status != self.ADL_OK:
            raise HardwareDisplayError(f"AMD ADL I2C read failed with status {status} (adapter={adapter}, output={output}, address=0x{address:02X}).")
        return bytes(buffer[: recv_size.value])

    def write_i2c(self, adapter: int, output: int, data: bytes) -> None:
        send = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        recv_size = ctypes.c_int(0)
        status = self.ADL_Display_DDCBlockAccess_Get(adapter, output, 0, 0, len(data), send, ctypes.byref(recv_size), None)
        if status != self.ADL_OK:
            raise HardwareDisplayError(f"AMD ADL I2C write failed with status {status} (adapter={adapter}, output={output}, address=0x{data[0]:02X}).")


def _list_amd_displays() -> list[HardwareDisplay]:
    amd = AmdLibrary()
    try:
        count = ctypes.c_int()
        if amd.ADL_Adapter_NumberOfAdapters_Get(ctypes.byref(count)) != amd.ADL_OK or count.value <= 0:
            return []
        adapters = (AmdAdapterInfo * count.value)()
        if amd.ADL_Adapter_AdapterInfo_Get(adapters, ctypes.sizeof(adapters)) != amd.ADL_OK:
            return []
        seen_paths: set[bytes] = set()
        displays: list[HardwareDisplay] = []
        for adapter in adapters:
            if not adapter.iPresent or adapter.strDriverPathExt in seen_paths:
                continue
            seen_paths.add(bytes(adapter.strDriverPathExt))
            display_count = ctypes.c_int()
            display_ptr = ctypes.POINTER(AmdDisplayInfo)()
            if amd.ADL_Display_DisplayInfo_Get(adapter.iAdapterIndex, ctypes.byref(display_count), ctypes.byref(display_ptr), 1) != amd.ADL_OK:
                continue
            for display_index in range(display_count.value):
                info = display_ptr[display_index]
                logical_index = info.displayID.iDisplayLogicalIndex
                item = _make_amd_display(amd, adapter.iAdapterIndex, logical_index)
                if item:
                    displays.append(item)
        return displays
    finally:
        # Keep the DLL initialized for closures by intentionally not closing; the process owns the handles.
        pass


def _make_amd_display(amd: AmdLibrary, adapter: int, output: int) -> HardwareDisplay | None:
    def read_i2c(address: int, size: int) -> bytes:
        return amd.read_i2c(adapter, output, address, size)

    def write_i2c(data: bytes) -> None:
        amd.write_i2c(adapter, output, data)

    try:
        edid = HardwareDisplay("AMD", str(adapter), str(output), "Unknown Display", None, read_i2c, write_i2c).read_edid()
    except HardwareDisplayError as exc:
        log_notice("AMD display EDID read failed during enumeration", adapter=adapter, output=output, error=exc)
        return None
    return HardwareDisplay("AMD", str(adapter), str(output), edid.name() or "Unknown Display", edid.product_id(), read_i2c, write_i2c, edid=edid)


class NV_I2C_SPEED(IntEnum):
    DEFAULT = 0
    KHZ_3 = 1
    KHZ_10 = 2
    KHZ_33 = 3
    KHZ_100 = 4
    KHZ_200 = 5
    KHZ_400 = 6


class NV_I2C_INFO(ctypes.Structure):
    _fields_ = [
        ("version", wintypes.DWORD),
        ("displayMask", wintypes.DWORD),
        ("bIsDDCPort", wintypes.BYTE),
        ("i2cDevAddress", wintypes.BYTE),
        ("pbI2cRegAddress", ctypes.POINTER(wintypes.BYTE)),
        ("regAddrSize", wintypes.DWORD),
        ("pbData", ctypes.POINTER(wintypes.BYTE)),
        ("cbSize", wintypes.DWORD),
        ("i2cSpeed", wintypes.DWORD),
        ("i2cSpeedKhz", ctypes.c_int),
    ]


NVAPI_OK = 0
NVAPI_MAX_PHYSICAL_GPUS = 64
NVAPI_I2C_SPEED_DEPRECATED = 0xFFFF
NV_I2C_INFO_VER = ctypes.sizeof(NV_I2C_INFO) | (2 << 16)


class NvidiaLibrary:
    def __init__(self) -> None:
        require_windows()
        self.dll = self._load_library("nvapi.dll", "nvapi64.dll")
        self.query_interface = self.dll.nvapi_QueryInterface
        self.query_interface.argtypes = [wintypes.DWORD]
        self.query_interface.restype = ctypes.c_void_p
        self._bind()
        if self.NvAPI_Initialize() != NVAPI_OK:
            raise HardwareDisplayError("NvAPI_Initialize failed.")

    def _load_library(self, *names: str) -> ctypes.WinDLL:
        for name in names:
            try:
                return ctypes.WinDLL(name)
            except OSError as exc:
                log_notice("NVIDIA NVAPI library load attempt failed", library=name, error=exc)
                continue
        raise HardwareDisplayError("NVIDIA NVAPI library not found.")

    def _function(self, function_id: int, restype: object, argtypes: list[object]) -> object:
        pointer = self.query_interface(function_id)
        if not pointer:
            raise HardwareDisplayError(f"NvAPI function 0x{function_id:08X} not found.")
        prototype = ctypes.WINFUNCTYPE(restype, *argtypes)
        return prototype(pointer)

    def _bind(self) -> None:
        gpu_array = ctypes.c_void_p * NVAPI_MAX_PHYSICAL_GPUS
        self.NvAPI_Initialize = self._function(0x0150E828, ctypes.c_int, [])
        self.NvAPI_EnumPhysicalGPUs = self._function(
            0xE5AC921F,
            ctypes.c_int,
            [gpu_array, ctypes.POINTER(wintypes.DWORD)],
        )
        self.NvAPI_GPU_GetConnectedOutputs = self._function(
            0x1730BFC9,
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)],
        )
        self.NvAPI_I2CRead = self._function(
            0x2FDE12C5,
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.POINTER(NV_I2C_INFO)],
        )
        self.NvAPI_I2CWrite = self._function(
            0xE812EB07,
            ctypes.c_int,
            [ctypes.c_void_p, ctypes.POINTER(NV_I2C_INFO)],
        )

    def read_i2c(self, gpu: int, output: int, address: int, size: int) -> bytes:
        buffer = (wintypes.BYTE * size)()
        info = NV_I2C_INFO(
            version=NV_I2C_INFO_VER,
            displayMask=output,
            bIsDDCPort=1,
            i2cDevAddress=address,
            pbI2cRegAddress=None,
            regAddrSize=0,
            pbData=buffer,
            cbSize=size,
            i2cSpeed=NVAPI_I2C_SPEED_DEPRECATED,
            i2cSpeedKhz=NV_I2C_SPEED.KHZ_10,
        )
        status = self.NvAPI_I2CRead(gpu, ctypes.byref(info))
        if status != NVAPI_OK:
            raise HardwareDisplayError(f"NVIDIA NVAPI I2C read failed with status {status} (output=0x{output:X}, address=0x{address:02X}).")
        return bytes(buffer)

    def write_i2c(self, gpu: int, output: int, data: bytes) -> None:
        payload = (wintypes.BYTE * (len(data) - 1)).from_buffer_copy(data[1:])
        info = NV_I2C_INFO(
            version=NV_I2C_INFO_VER,
            displayMask=output,
            bIsDDCPort=1,
            i2cDevAddress=data[0],
            pbI2cRegAddress=None,
            regAddrSize=0,
            pbData=payload,
            cbSize=len(data) - 1,
            i2cSpeed=NVAPI_I2C_SPEED_DEPRECATED,
            i2cSpeedKhz=NV_I2C_SPEED.KHZ_10,
        )
        status = self.NvAPI_I2CWrite(gpu, ctypes.byref(info))
        if status != NVAPI_OK:
            raise HardwareDisplayError(f"NVIDIA NVAPI I2C write failed with status {status} (output=0x{output:X}, address=0x{data[0]:02X}).")


def _list_nvidia_displays() -> list[HardwareDisplay]:
    nvidia = NvidiaLibrary()
    gpu_array_type = ctypes.c_void_p * NVAPI_MAX_PHYSICAL_GPUS
    gpus = gpu_array_type()
    count = wintypes.DWORD()
    if nvidia.NvAPI_EnumPhysicalGPUs(gpus, ctypes.byref(count)) != NVAPI_OK:
        return []
    displays: list[HardwareDisplay] = []
    for index in range(count.value):
        gpu = gpus[index]
        outputs = wintypes.DWORD()
        if nvidia.NvAPI_GPU_GetConnectedOutputs(gpu, ctypes.byref(outputs)) != NVAPI_OK:
            continue
        output = 1
        while output:
            if outputs.value & output:
                item = _make_nvidia_display(nvidia, gpu, index, output)
                if item:
                    displays.append(item)
            output <<= 1
            if output > (1 << 31):
                break
    return displays


def _make_nvidia_display(nvidia: NvidiaLibrary, gpu: int, gpu_index: int, output: int) -> HardwareDisplay | None:
    def read_i2c(address: int, size: int) -> bytes:
        return nvidia.read_i2c(gpu, output, address, size)

    def write_i2c(data: bytes) -> None:
        nvidia.write_i2c(gpu, output, data)

    try:
        edid = HardwareDisplay("NVIDIA", str(gpu_index), f"0x{output:X}", "Unknown Display", None, read_i2c, write_i2c).read_edid()
    except HardwareDisplayError as exc:
        log_notice("NVIDIA display EDID read failed during enumeration", gpu_index=gpu_index, output=output, error=exc)
        return None
    return HardwareDisplay("NVIDIA", str(gpu_index), f"0x{output:X}", edid.name() or "Unknown Display", edid.product_id(), read_i2c, write_i2c, edid=edid)
