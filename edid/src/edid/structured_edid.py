from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from edid.edid_data import EDID_BLOCK_SIZE, DisplayData, DisplayDataError


class CEADataBlockTag(IntEnum):
    RESERVED = 0
    AUDIO = 1
    VIDEO = 2
    VENDOR_SPECIFIC = 3
    SPEAKER_ALLOCATION = 4
    VESA_DTC = 5
    EXTENDED = 7


CEA_EXTENDED_TAGS = {
    0x00: "Video Capability",
    0x01: "Vendor-Specific Video",
    0x02: "VESA Display Device",
    0x03: "VESA Video Timing Block Extension",
    0x04: "Reserved HDMI Video",
    0x05: "Colorimetry",
    0x06: "HDR Static Metadata",
    0x07: "HDR Dynamic Metadata",
    0x0D: "Video Format Preference",
    0x0E: "YCbCr 4:2:0 Video",
    0x0F: "YCbCr 4:2:0 Capability Map",
    0x12: "HDMI Audio",
    0x13: "Room Configuration",
    0x14: "Speaker Location",
    0x20: "InfoFrame",
    0x21: "DisplayID Type VII Video Timing",
    0x22: "DisplayID Type VIII Video Timing",
    0x23: "DisplayID Type X Video Timing",
    0x24: "HDMI Forum VSDB",
    0x25: "HDMI Forum SCDB",
}


ASPECT_RATIOS = {
    0: (16, 10),
    1: (4, 3),
    2: (5, 4),
    3: (16, 9),
}


@dataclass
class BaseDisplayProperties:
    manufacturer_id: str
    product_code: int
    serial_number: int
    manufacture_week: int
    manufacture_year: int
    edid_version: tuple[int, int]
    digital_input: bool
    bit_depth: int | None
    video_interface: int | None
    analog_signal_level: int | None
    separate_sync: bool
    composite_sync: bool
    sync_on_green: bool
    width_cm: int
    height_cm: int
    gamma: float | None
    chromaticity: dict[str, tuple[float, float]]
    standby: bool
    suspend: bool
    active_off: bool
    srgb: bool
    preferred_timing: bool
    continuous_frequency: bool
    extension_count: int
    name: str | None
    serial_text: str | None
    range_limits: bytes | None


@dataclass
class StandardTiming:
    index: int
    width: int
    height: int
    refresh_rate: int
    aspect: tuple[int, int]
    raw: bytes

    @classmethod
    def unused(cls, index: int) -> StandardTiming:
        return cls(index=index, width=0, height=0, refresh_rate=0, aspect=(0, 0), raw=b"\x01\x01")

    @property
    def is_used(self) -> bool:
        return self.raw not in {b"\x01\x01", b"\x00\x00"}

    def encode(self) -> bytes:
        if not self.is_used:
            return b"\x01\x01"
        width_code = max(0, min(255, self.width // 8 - 31))
        ratio_index = next((key for key, value in ASPECT_RATIOS.items() if value == self.aspect), 3)
        refresh_code = max(0, min(63, self.refresh_rate - 60))
        return bytes([width_code, (ratio_index << 6) | refresh_code])


@dataclass
class DetailedTiming:
    pixel_clock_khz: int
    h_active: int
    h_blanking: int
    v_active: int
    v_blanking: int
    h_sync_offset: int
    h_sync_width: int
    v_sync_offset: int
    v_sync_width: int
    h_size_mm: int
    v_size_mm: int
    h_border: int
    v_border: int
    interlaced: bool
    stereo: int
    sync_type: int
    positive_hsync: bool
    positive_vsync: bool
    raw: bytes

    @property
    def refresh_rate(self) -> float | None:
        total_pixels = (self.h_active + self.h_blanking) * (self.v_active + self.v_blanking)
        if total_pixels <= 0:
            return None
        return self.pixel_clock_khz * 1000 / total_pixels

    def encode(self) -> bytes:
        data = bytearray(18)
        data[0:2] = int(self.pixel_clock_khz // 10).to_bytes(2, "little")
        data[2] = self.h_active & 0xFF
        data[3] = self.h_blanking & 0xFF
        data[4] = ((self.h_active >> 8) << 4) | (self.h_blanking >> 8)
        data[5] = self.v_active & 0xFF
        data[6] = self.v_blanking & 0xFF
        data[7] = ((self.v_active >> 8) << 4) | (self.v_blanking >> 8)
        data[8] = self.h_sync_offset & 0xFF
        data[9] = self.h_sync_width & 0xFF
        data[10] = ((self.v_sync_offset & 0x0F) << 4) | (self.v_sync_width & 0x0F)
        data[11] = (
            ((self.h_sync_offset >> 8) << 6)
            | ((self.h_sync_width >> 8) << 4)
            | ((self.v_sync_offset >> 4) << 2)
            | (self.v_sync_width >> 4)
        )
        data[12] = self.h_size_mm & 0xFF
        data[13] = self.v_size_mm & 0xFF
        data[14] = ((self.h_size_mm >> 8) << 4) | (self.v_size_mm >> 8)
        data[15] = self.h_border & 0xFF
        data[16] = self.v_border & 0xFF
        data[17] = (
            (0x80 if self.interlaced else 0)
            | ((self.stereo & 0x03) << 5)
            | ((self.sync_type & 0x03) << 3)
            | (0x04 if self.positive_vsync else 0)
            | (0x02 if self.positive_hsync else 0)
        )
        return bytes(data)


@dataclass
class MonitorDescriptor:
    tag: int
    text: str | None
    raw: bytes

    @property
    def name(self) -> str:
        return {
            0xFC: "Monitor Name",
            0xFF: "Serial Number",
            0xFE: "Unspecified Text",
            0xFD: "Range Limits",
        }.get(self.tag, f"Descriptor 0x{self.tag:02X}")

    def encode(self) -> bytes:
        if self.text is None:
            return self.raw[:18].ljust(18, b"\x00")
        text = self.text.encode("latin1", errors="replace")[:13]
        return b"\x00\x00\x00" + bytes([self.tag, 0x00]) + text.ljust(13, b" ")


@dataclass
class CEADataBlock:
    tag: int
    payload: bytes

    @property
    def extended_tag(self) -> int | None:
        if self.tag == CEADataBlockTag.EXTENDED and self.payload:
            return self.payload[0]
        return None

    @property
    def name(self) -> str:
        if self.tag == CEADataBlockTag.EXTENDED:
            if self.extended_tag is None:
                return "Extended"
            return CEA_EXTENDED_TAGS.get(self.extended_tag, f"Extended 0x{self.extended_tag:02X}")
        return {
            CEADataBlockTag.AUDIO: "Audio",
            CEADataBlockTag.VIDEO: "Video",
            CEADataBlockTag.VENDOR_SPECIFIC: "Vendor Specific",
            CEADataBlockTag.SPEAKER_ALLOCATION: "Speaker Allocation",
            CEADataBlockTag.VESA_DTC: "VESA DTC",
        }.get(CEADataBlockTag(self.tag) if self.tag in CEADataBlockTag._value2member_map_ else self.tag, f"Tag {self.tag}")

    @property
    def oui(self) -> int | None:
        if self.tag != CEADataBlockTag.VENDOR_SPECIFIC or len(self.payload) < 3:
            return None
        return self.payload[0] | (self.payload[1] << 8) | (self.payload[2] << 16)

    def encode(self) -> bytes:
        if len(self.payload) > 31:
            raise DisplayDataError("CEA data block payloads cannot exceed 31 bytes.")
        return bytes([(self.tag << 5) | len(self.payload)]) + self.payload


@dataclass
class ExtensionBlock:
    index: int
    tag: int
    revision: int
    dtd_offset: int
    flags: int
    data_blocks: list[CEADataBlock] = field(default_factory=list)
    detailed_timings: list[DetailedTiming] = field(default_factory=list)
    raw: bytes = b""

    @property
    def type_name(self) -> str:
        return {
            0x02: "CEA-861",
            0x10: "VTB-EXT",
            0x40: "DisplayID",
            0x70: "DisplayID 2.0",
            0xF0: "Block Map",
            0xFF: "Manufacturer Extension",
        }.get(self.tag, f"Extension 0x{self.tag:02X}")

    def encode(self) -> bytes:
        if self.tag != 0x02:
            data = bytearray(self.raw[:EDID_BLOCK_SIZE].ljust(EDID_BLOCK_SIZE, b"\x00"))
            data[0] = self.tag
            data[1] = self.revision
            data[127] = (-sum(data[:127])) & 0xFF
            return bytes(data)

        payload = b"".join(block.encode() for block in self.data_blocks)
        if len(payload) > 123:
            raise DisplayDataError("CEA data blocks exceed available extension space.")
        dtd_offset = max(4 + len(payload), self.dtd_offset or 4 + len(payload))
        if dtd_offset > 127:
            raise DisplayDataError("CEA detailed timing offset exceeds block size.")
        data = bytearray(EDID_BLOCK_SIZE)
        data[0] = 0x02
        data[1] = self.revision
        data[2] = dtd_offset
        data[3] = self.flags
        data[4 : 4 + len(payload)] = payload
        offset = dtd_offset
        for timing in self.detailed_timings:
            if offset + 18 > 127:
                raise DisplayDataError("CEA detailed timings exceed extension space.")
            data[offset : offset + 18] = timing.encode()
            offset += 18
        data[127] = (-sum(data[:127])) & 0xFF
        return bytes(data)

    def bytes_used(self) -> int:
        if self.tag == 0x02:
            return 4 + sum(1 + len(block.payload) for block in self.data_blocks) + len(self.detailed_timings) * 18
        return len(self.raw[:EDID_BLOCK_SIZE].rstrip(b"\x00"))

    def bytes_left(self) -> int:
        return max(0, 127 - self.bytes_used())


@dataclass
class StructuredEDID:
    properties: BaseDisplayProperties
    established_timings: bytes
    standard_timings: list[StandardTiming]
    detailed_timings: list[DetailedTiming]
    descriptors: list[MonitorDescriptor]
    extensions: list[ExtensionBlock]
    raw: bytes

    @classmethod
    def parse(cls, display_data: DisplayData) -> StructuredEDID:
        if not display_data.is_edid or display_data.size < EDID_BLOCK_SIZE:
            raise DisplayDataError("Structured EDID parsing requires EDID data.")
        data = display_data.data
        base = data[:EDID_BLOCK_SIZE]
        properties = _parse_base_properties(display_data, base)
        standard_timings = [_parse_standard_timing(index, base[38 + index * 2 : 40 + index * 2]) for index in range(8)]
        detailed_timings: list[DetailedTiming] = []
        descriptors: list[MonitorDescriptor] = []
        for slot in range(4):
            raw = base[54 + slot * 18 : 72 + slot * 18]
            if raw[:2] != b"\x00\x00":
                detailed_timings.append(_parse_detailed_timing(raw))
            else:
                descriptors.append(_parse_descriptor(raw))
        extensions = []
        for block_index in range(1, min(base[126] + 1, len(data) // EDID_BLOCK_SIZE)):
            raw = data[block_index * EDID_BLOCK_SIZE : (block_index + 1) * EDID_BLOCK_SIZE]
            extensions.append(_parse_extension(block_index, raw))
        return cls(
            properties=properties,
            established_timings=base[35:38],
            standard_timings=standard_timings,
            detailed_timings=detailed_timings,
            descriptors=descriptors,
            extensions=extensions,
            raw=data,
        )

    def encode(self) -> DisplayData:
        base = bytearray(self.raw[:EDID_BLOCK_SIZE])
        base[35:38] = self.established_timings[:3].ljust(3, b"\x00")
        for index, timing in enumerate(self.standard_timings[:8]):
            base[38 + index * 2 : 40 + index * 2] = timing.encode()
        descriptor_slots = [timing.encode() for timing in self.detailed_timings[:4]]
        descriptor_slots.extend(descriptor.encode() for descriptor in self.descriptors[: 4 - len(descriptor_slots)])
        descriptor_slots.extend([bytes(18)] * (4 - len(descriptor_slots)))
        for slot, descriptor in enumerate(descriptor_slots[:4]):
            base[54 + slot * 18 : 72 + slot * 18] = descriptor
        base[126] = len(self.extensions)
        base[127] = (-sum(base[:127])) & 0xFF
        blocks = [bytes(base)] + [extension.encode() for extension in self.extensions]
        return DisplayData(b"".join(blocks))

    def preferred_timing(self) -> DetailedTiming | None:
        return self.detailed_timings[0] if self.detailed_timings else None

    def set_preferred_timing(self, index: int) -> None:
        if index < 0 or index >= len(self.detailed_timings):
            raise DisplayDataError("Preferred timing index is out of range.")
        timing = self.detailed_timings.pop(index)
        self.detailed_timings.insert(0, timing)

    def set_descriptor_enabled(self, tag: int, enabled: bool) -> None:
        if enabled:
            if not any(descriptor.tag == tag for descriptor in self.descriptors):
                self.descriptors.append(MonitorDescriptor(tag=tag, text="", raw=b"\x00\x00\x00" + bytes([tag, 0]) + bytes(13)))
            return
        self.descriptors = [descriptor for descriptor in self.descriptors if descriptor.tag != tag]

    def add_extension(self, extension: ExtensionBlock) -> None:
        if len(self.extensions) >= 8:
            raise DisplayDataError("EDID cannot contain more than 8 extension blocks in this editor.")
        extension.index = len(self.extensions) + 1
        self.extensions.append(extension)

    def delete_extension(self, index: int) -> None:
        del self.extensions[index]
        for offset, extension in enumerate(self.extensions, start=1):
            extension.index = offset

    def move_extension(self, index: int, direction: int) -> int:
        target = index + direction
        if target < 0 or target >= len(self.extensions):
            return index
        self.extensions[index], self.extensions[target] = self.extensions[target], self.extensions[index]
        for offset, extension in enumerate(self.extensions, start=1):
            extension.index = offset
        return target

    def summary_lines(self) -> list[str]:
        props = self.properties
        lines = [
            f"Manufacturer/Product: {props.manufacturer_id}{props.product_code:04X}",
            f"Name: {props.name or 'unknown'}",
            f"EDID version: {props.edid_version[0]}.{props.edid_version[1]}",
            f"Input: {'digital' if props.digital_input else 'analog'}",
            f"Size: {props.width_cm} x {props.height_cm} cm",
            f"Extensions: {len(self.extensions)}",
            f"Detailed timings: {len(self.detailed_timings)}",
            f"Standard timings: {sum(1 for timing in self.standard_timings if timing.is_used)}",
        ]
        for extension in self.extensions:
            lines.append(
                f"Extension {extension.index}: {extension.type_name}, "
                f"{len(extension.data_blocks)} data blocks, {len(extension.detailed_timings)} DTDs"
            )
        return lines


def _parse_base_properties(display_data: DisplayData, base: bytes) -> BaseDisplayProperties:
    features = base[24]
    input_byte = base[20]
    digital_input = bool(input_byte & 0x80)
    bit_depth = None
    video_interface = None
    if digital_input:
        depth_code = (input_byte >> 4) & 0x07
        bit_depth = {1: 6, 2: 8, 3: 10, 4: 12, 5: 14, 6: 16}.get(depth_code)
        video_interface = input_byte & 0x0F
        analog_signal_level = None
        separate_sync = False
        composite_sync = False
        sync_on_green = False
    else:
        analog_signal_level = (input_byte >> 5) & 0x03
        separate_sync = bool(input_byte & 0x08)
        composite_sync = bool(input_byte & 0x04)
        sync_on_green = bool(input_byte & 0x02)
    gamma = None if base[23] == 0xFF else (base[23] + 100) / 100
    return BaseDisplayProperties(
        manufacturer_id=display_data._edid_product_id()[:3],
        product_code=base[10] | (base[11] << 8),
        serial_number=int.from_bytes(base[12:16], "little"),
        manufacture_week=base[16],
        manufacture_year=base[17] + 1990,
        edid_version=(base[18], base[19]),
        digital_input=digital_input,
        bit_depth=bit_depth,
        video_interface=video_interface,
        analog_signal_level=analog_signal_level,
        separate_sync=separate_sync,
        composite_sync=composite_sync,
        sync_on_green=sync_on_green,
        width_cm=base[21],
        height_cm=base[22],
        gamma=gamma,
        chromaticity=_parse_chromaticity(base),
        standby=bool(features & 0x80),
        suspend=bool(features & 0x40),
        active_off=bool(features & 0x20),
        srgb=bool(features & 0x04),
        preferred_timing=bool(features & 0x02),
        continuous_frequency=bool(features & 0x01),
        extension_count=base[126],
        name=display_data.name(),
        serial_text=display_data._edid_name(0xFF),
        range_limits=next(
            (base[54 + slot * 18 : 72 + slot * 18] for slot in range(4) if base[54 + slot * 18 + 3] == 0xFD),
            None,
        ),
    )


def _parse_chromaticity(base: bytes) -> dict[str, tuple[float, float]]:
    low = base[25:27]
    values = {
        "red_x": ((base[27] << 2) | ((low[0] >> 6) & 0x03)) / 1024,
        "red_y": ((base[28] << 2) | ((low[0] >> 4) & 0x03)) / 1024,
        "green_x": ((base[29] << 2) | ((low[0] >> 2) & 0x03)) / 1024,
        "green_y": ((base[30] << 2) | (low[0] & 0x03)) / 1024,
        "blue_x": ((base[31] << 2) | ((low[1] >> 6) & 0x03)) / 1024,
        "blue_y": ((base[32] << 2) | ((low[1] >> 4) & 0x03)) / 1024,
        "white_x": ((base[33] << 2) | ((low[1] >> 2) & 0x03)) / 1024,
        "white_y": ((base[34] << 2) | (low[1] & 0x03)) / 1024,
    }
    return {
        "red": (values["red_x"], values["red_y"]),
        "green": (values["green_x"], values["green_y"]),
        "blue": (values["blue_x"], values["blue_y"]),
        "white": (values["white_x"], values["white_y"]),
    }


def _parse_standard_timing(index: int, raw: bytes) -> StandardTiming:
    if raw in {b"\x01\x01", b"\x00\x00"}:
        return StandardTiming.unused(index)
    width = (raw[0] + 31) * 8
    aspect = ASPECT_RATIOS[(raw[1] >> 6) & 0x03]
    height = round(width * aspect[1] / aspect[0])
    refresh = (raw[1] & 0x3F) + 60
    return StandardTiming(index=index, width=width, height=height, refresh_rate=refresh, aspect=aspect, raw=raw)


def _parse_detailed_timing(raw: bytes) -> DetailedTiming:
    flags = raw[17]
    return DetailedTiming(
        pixel_clock_khz=int.from_bytes(raw[0:2], "little") * 10,
        h_active=raw[2] | ((raw[4] >> 4) << 8),
        h_blanking=raw[3] | ((raw[4] & 0x0F) << 8),
        v_active=raw[5] | ((raw[7] >> 4) << 8),
        v_blanking=raw[6] | ((raw[7] & 0x0F) << 8),
        h_sync_offset=raw[8] | (((raw[11] >> 6) & 0x03) << 8),
        h_sync_width=raw[9] | (((raw[11] >> 4) & 0x03) << 8),
        v_sync_offset=((raw[10] >> 4) & 0x0F) | (((raw[11] >> 2) & 0x03) << 4),
        v_sync_width=(raw[10] & 0x0F) | ((raw[11] & 0x03) << 4),
        h_size_mm=raw[12] | ((raw[14] >> 4) << 8),
        v_size_mm=raw[13] | ((raw[14] & 0x0F) << 8),
        h_border=raw[15],
        v_border=raw[16],
        interlaced=bool(flags & 0x80),
        stereo=(flags >> 5) & 0x03,
        sync_type=(flags >> 3) & 0x03,
        positive_hsync=bool(flags & 0x02),
        positive_vsync=bool(flags & 0x04),
        raw=raw,
    )


def _parse_descriptor(raw: bytes) -> MonitorDescriptor:
    tag = raw[3]
    text = None
    if tag in {0xFC, 0xFF, 0xFE}:
        text = raw[5:18].split(b"\x0A", 1)[0].split(b"\x00", 1)[0].decode("latin1", errors="replace").rstrip()
    return MonitorDescriptor(tag=tag, text=text, raw=raw)


def _parse_extension(index: int, raw: bytes) -> ExtensionBlock:
    if raw[0] != 0x02:
        return ExtensionBlock(index=index, tag=raw[0], revision=raw[1], dtd_offset=0, flags=0, raw=raw)
    dtd_offset = raw[2] if raw[2] else 127
    data_blocks = []
    cursor = 4
    while cursor < dtd_offset and cursor < 127:
        header = raw[cursor]
        length = header & 0x1F
        tag = header >> 5
        payload = raw[cursor + 1 : cursor + 1 + length]
        if len(payload) != length:
            break
        data_blocks.append(CEADataBlock(tag=tag, payload=payload))
        cursor += 1 + length
    detailed_timings = []
    cursor = dtd_offset
    while cursor + 18 <= 127:
        timing_raw = raw[cursor : cursor + 18]
        if timing_raw == bytes(18):
            break
        if timing_raw[:2] != b"\x00\x00":
            detailed_timings.append(_parse_detailed_timing(timing_raw))
        cursor += 18
    return ExtensionBlock(
        index=index,
        tag=raw[0],
        revision=raw[1],
        dtd_offset=dtd_offset,
        flags=raw[3],
        data_blocks=data_blocks,
        detailed_timings=detailed_timings,
        raw=raw,
    )
