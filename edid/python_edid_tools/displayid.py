from __future__ import annotations

from dataclasses import dataclass, field

from .edid_data import DISPLAYID_BLOCK_SIZE, DisplayData, DisplayDataError


DISPLAYID_TAGS = {
    0x00: "Product Identification",
    0x01: "Display Parameters",
    0x02: "Color Characteristics",
    0x03: "Type I Detailed Timings",
    0x04: "Type II Detailed Timings",
    0x05: "Type III Short Timings",
    0x06: "Type IV DMT Timings",
    0x07: "VESA Timings",
    0x08: "CEA Timings",
    0x09: "Video Timing Range Limits",
    0x0A: "Product Serial Number",
    0x0B: "General Purpose ASCII String",
    0x0C: "Display Device Data",
    0x0D: "Interface Power Sequencing",
    0x0E: "Transfer Characteristics",
    0x0F: "Display Interface",
    0x10: "Stereo Display Interface",
    0x12: "Tiled Display Topology",
    0x20: "Product Identification 2.0",
    0x21: "Display Parameters 2.0",
    0x22: "Type VII Detailed Timings",
    0x23: "Type VIII Enumerated Timings",
    0x24: "Type X Formula Timings",
    0x25: "Dynamic Video Timing Range Limits",
    0x26: "Display Interface Features",
    0x27: "Stereo Display Interface 2.0",
    0x28: "Tiled Display Topology 2.0",
    0x29: "Container ID",
    0x2A: "Adaptive Sync",
}


@dataclass
class DisplayIDDataBlock:
    tag: int
    revision: int
    payload: bytes

    @property
    def name(self) -> str:
        return DISPLAYID_TAGS.get(self.tag, f"Data Block 0x{self.tag:02X}")

    def encode(self) -> bytes:
        if len(self.payload) > 255:
            raise DisplayDataError("DisplayID data block payloads cannot exceed 255 bytes.")
        return bytes([self.tag & 0xFF, self.revision & 0xFF, len(self.payload) & 0xFF]) + self.payload


@dataclass
class DisplayIDProductIdentification:
    manufacturer: str | None
    product_code: int | None
    serial_number: int | None
    manufacture_week: int | None
    manufacture_year: int | None
    name: str | None
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDProductIdentification:
        data = block.payload
        manufacturer = None
        product = None
        serial = None
        week = None
        year = None
        name = None
        if len(data) >= 5 and all(0x20 <= byte <= 0x7E for byte in data[:3]):
            manufacturer = data[:3].decode("latin1")
            product = int.from_bytes(data[3:5], "little")
        elif len(data) >= 5:
            manufacturer = data[:3].hex().upper()
            product = int.from_bytes(data[3:5], "little")
        if len(data) >= 9:
            serial = int.from_bytes(data[5:9], "little")
        if len(data) >= 11:
            week = data[9]
            year = data[10] + 2000
        if len(data) >= 12:
            raw_name = data[11:].split(b"\x00", 1)[0]
            if raw_name:
                name = raw_name.decode("latin1", errors="replace").rstrip()
        return cls(manufacturer, product, serial, week, year, name, data)


@dataclass
class DisplayIDString:
    tag: int
    text: str
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDString:
        return cls(block.tag, block.payload.split(b"\x00", 1)[0].decode("latin1", errors="replace").rstrip(), block.payload)


@dataclass
class DisplayIDRangeLimits:
    minimum_vertical_hz: int | None
    maximum_vertical_hz: int | None
    minimum_horizontal_khz: int | None
    maximum_horizontal_khz: int | None
    maximum_pixel_clock_mhz: int | None
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDRangeLimits:
        data = block.payload
        values = [data[index] if index < len(data) else None for index in range(5)]
        return cls(values[0], values[1], values[2], values[3], values[4] * 10 if values[4] is not None else None, data)


@dataclass
class DisplayIDDisplayParameters:
    image_width_mm: int | None
    image_height_mm: int | None
    feature_flags: int
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDDisplayParameters:
        data = block.payload
        width = int.from_bytes(data[0:2], "little") if len(data) >= 2 else None
        height = int.from_bytes(data[2:4], "little") if len(data) >= 4 else None
        flags = data[4] if len(data) >= 5 else 0
        return cls(width, height, flags, data)


@dataclass
class DisplayIDColorCharacteristics:
    raw_coordinates: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDColorCharacteristics:
        return cls(block.payload)


@dataclass
class DisplayIDInterfaceBlock:
    interface_type: int | None
    interface_version: int | None
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDInterfaceBlock:
        data = block.payload
        return cls(data[0] if data else None, data[1] if len(data) > 1 else None, data)


@dataclass
class DisplayIDStereoInterfaceBlock:
    stereo_flags: int
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDStereoInterfaceBlock:
        return cls(block.payload[0] if block.payload else 0, block.payload)


@dataclass
class DisplayIDTimingBlock:
    timing_type: int
    records: list[bytes]
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDTimingBlock:
        record_size = {
            0x03: 20,
            0x04: 11,
            0x05: 3,
            0x06: 1,
            0x07: 1,
            0x08: 1,
            0x22: 20,
            0x23: 4,
            0x24: 7,
        }.get(block.tag, len(block.payload) or 1)
        records = [block.payload[index : index + record_size] for index in range(0, len(block.payload), record_size)]
        return cls(block.tag, [record for record in records if len(record) == record_size], block.payload)


@dataclass
class DisplayIDEmbeddedCEA:
    blocks: list[bytes]
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDEmbeddedCEA:
        return cls([block.payload], block.payload)


@dataclass
class DisplayIDContainerID:
    uuid_bytes: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> DisplayIDContainerID:
        return cls(block.payload[:16])

    @property
    def hex(self) -> str:
        return self.uuid_bytes.hex()


@dataclass
class TiledDisplayTopology:
    capabilities: int
    columns: int
    rows: int
    location_column: int
    location_row: int
    tile_width: int | None
    tile_height: int | None
    raw: bytes

    @classmethod
    def parse(cls, block: DisplayIDDataBlock) -> TiledDisplayTopology:
        data = block.payload
        columns = (data[1] & 0x0F) + 1 if len(data) > 1 else 1
        rows = ((data[1] >> 4) & 0x0F) + 1 if len(data) > 1 else 1
        location_column = data[2] & 0x0F if len(data) > 2 else 0
        location_row = (data[2] >> 4) & 0x0F if len(data) > 2 else 0
        width = int.from_bytes(data[3:5], "little") if len(data) >= 5 else None
        height = int.from_bytes(data[5:7], "little") if len(data) >= 7 else None
        return cls(data[0] if data else 0, columns, rows, location_column, location_row, width, height, data)


@dataclass
class DisplayIDDocument:
    version: int
    revision: int
    product_type: int
    extension_count: int
    blocks: list[DisplayIDDataBlock] = field(default_factory=list)
    raw: bytes = b""

    @classmethod
    def parse(cls, display_data: DisplayData) -> DisplayIDDocument:
        if not display_data.is_displayid:
            raise DisplayDataError("DisplayID parsing requires DisplayID data.")
        data = display_data.data
        size = display_data.displayid_block_size(0)
        if size < 5:
            raise DisplayDataError("Invalid DisplayID block size.")
        blocks: list[DisplayIDDataBlock] = []
        index = 4
        end = size - 1
        while index + 3 <= end:
            tag = data[index]
            revision = data[index + 1]
            length = data[index + 2]
            start = index + 3
            stop = start + length
            if stop > end:
                break
            blocks.append(DisplayIDDataBlock(tag, revision, data[start:stop]))
            index = stop
        return cls(version=data[0], revision=data[1], product_type=data[2], extension_count=data[3], blocks=blocks, raw=data[:size])

    def encode(self) -> DisplayData:
        payload = b"".join(block.encode() for block in self.blocks)
        size = len(payload) + 5
        if size > DISPLAYID_BLOCK_SIZE:
            raise DisplayDataError("DisplayID payload exceeds one 256-byte block.")
        data = bytearray(DISPLAYID_BLOCK_SIZE)
        data[0] = self.version
        data[1] = len(payload)
        data[2] = self.product_type
        data[3] = self.extension_count
        data[4 : 4 + len(payload)] = payload
        checksum_index = len(payload) + 4
        data[checksum_index] = (-sum(data[:checksum_index])) & 0xFF
        return DisplayData(bytes(data[: checksum_index + 1]))

    def typed_blocks(self) -> list[object]:
        typed: list[object] = []
        for block in self.blocks:
            if block.tag in {0x00, 0x20}:
                typed.append(DisplayIDProductIdentification.parse(block))
            elif block.tag in {0x01, 0x21}:
                typed.append(DisplayIDDisplayParameters.parse(block))
            elif block.tag == 0x02:
                typed.append(DisplayIDColorCharacteristics.parse(block))
            elif block.tag in {0x03, 0x04, 0x05, 0x06, 0x07, 0x22, 0x23, 0x24}:
                typed.append(DisplayIDTimingBlock.parse(block))
            elif block.tag in {0x0A, 0x0B}:
                typed.append(DisplayIDString.parse(block))
            elif block.tag in {0x09, 0x25}:
                typed.append(DisplayIDRangeLimits.parse(block))
            elif block.tag in {0x0F, 0x26}:
                typed.append(DisplayIDInterfaceBlock.parse(block))
            elif block.tag in {0x10, 0x27}:
                typed.append(DisplayIDStereoInterfaceBlock.parse(block))
            elif block.tag in {0x12, 0x28}:
                typed.append(TiledDisplayTopology.parse(block))
            elif block.tag == 0x08:
                typed.append(DisplayIDEmbeddedCEA.parse(block))
            elif block.tag == 0x29:
                typed.append(DisplayIDContainerID.parse(block))
            else:
                typed.append(block)
        return typed

    def summary_lines(self) -> list[str]:
        lines = [
            f"DisplayID version: 0x{self.version:02X}",
            f"Product type: 0x{self.product_type:02X}",
            f"Extensions: {self.extension_count}",
            f"Data blocks: {len(self.blocks)}",
        ]
        for block in self.blocks:
            lines.append(f"- {block.name}: {len(block.payload)} bytes")
        return lines
