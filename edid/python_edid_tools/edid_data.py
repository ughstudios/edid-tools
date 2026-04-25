from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from .logging_utils import log_exception, log_notice


EDID_HEADER = bytes([0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])
EDID_BLOCK_SIZE = 128
DISPLAYID_BLOCK_SIZE = 256


class DisplayDataError(ValueError):
    """Raised when EDID/DisplayID data cannot be parsed or written."""


@dataclass
class DisplayData:
    """Container for EDID, DisplayID, or raw display data."""

    data: bytes
    original_size: int | None = None

    def __post_init__(self) -> None:
        self.data = bytes(self.data)
        if self.original_size is None:
            self.original_size = len(self.data)

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def reported_size(self) -> int:
        if self.is_edid:
            return self.data[126] * EDID_BLOCK_SIZE + EDID_BLOCK_SIZE

        if self.is_displayid:
            last_block_size = self.displayid_block_size(self.data[3])
            if last_block_size < 5:
                last_block_size = DISPLAYID_BLOCK_SIZE
            return self.data[3] * DISPLAYID_BLOCK_SIZE + last_block_size

        return self.size

    @property
    def is_edid(self) -> bool:
        if self.size < EDID_BLOCK_SIZE:
            return False
        return self.has_valid_edid_header or self.has_corrupted_edid_header

    @property
    def is_displayid(self) -> bool:
        size = self.displayid_block_size(0)
        if size < 5:
            return False

        index = 6
        used = 5
        end = size - 1
        while index < end:
            if index >= self.size:
                return False
            length = self.data[index] + 3
            used += length
            index += length

        return used <= size

    @property
    def has_valid_edid_header(self) -> bool:
        return self.size >= EDID_BLOCK_SIZE and self.data.startswith(EDID_HEADER)

    @property
    def has_corrupted_edid_header(self) -> bool:
        if self.size < EDID_BLOCK_SIZE:
            return False
        if self.data[18] != 1 or self.data[19] > 4:
            return False
        return self.is_valid_checksum(8, 120, add=6)

    @property
    def type_name(self) -> str:
        if self.is_edid:
            return "EDID"
        if self.is_displayid:
            return "DisplayID"
        return "Data"

    def clone(self) -> DisplayData:
        return DisplayData(self.data, self.original_size)

    def trim_to_reported_size(self, max_size: int | None = None) -> DisplayData:
        data = self.data
        reported_size = self.reported_size
        if len(data) > reported_size:
            data = data[:reported_size]
        if max_size is not None and len(data) > max_size:
            data = data[:max_size]
        return DisplayData(data, self.original_size)

    def displayid_block_size(self, block: int) -> int:
        if block < 0:
            return 0
        offset = block * DISPLAYID_BLOCK_SIZE
        if self.size < offset + 5:
            return 0
        if self.data[offset] < 0x10:
            return 0
        size = self.data[offset + 1] + 5
        if size > DISPLAYID_BLOCK_SIZE:
            return 0
        if self.size < offset + size:
            return 0
        return size

    def is_valid_edid_extension_block(self, block: int) -> bool:
        if block < 1:
            return False
        offset = block * EDID_BLOCK_SIZE
        block_data = self.data[offset : offset + EDID_BLOCK_SIZE]
        if len(block_data) < EDID_BLOCK_SIZE:
            return False
        if block_data.startswith(EDID_HEADER):
            return False
        if block_data[:127] == bytes(127):
            return False
        if block_data[:127] == bytes([0xFF]) * 127:
            return False
        return True

    def has_valid_edid_extension_blocks(self) -> bool:
        if self.size < EDID_BLOCK_SIZE:
            return False
        blocks = min(self.data[126] + 1, (self.size + 127) // 128)
        return all(self.is_valid_edid_extension_block(block) for block in range(1, blocks))

    def has_valid_edid_checksums(self) -> bool:
        if self.size < EDID_BLOCK_SIZE:
            return False
        if not self.is_valid_checksum(0, EDID_BLOCK_SIZE):
            return False
        blocks = min(self.data[126] + 1, self.size // EDID_BLOCK_SIZE)
        for block in range(1, blocks):
            if self.is_valid_edid_extension_block(block):
                if not self.is_valid_checksum(block * EDID_BLOCK_SIZE, EDID_BLOCK_SIZE):
                    return False
        return True

    def has_valid_displayid_checksums(self) -> bool:
        if self.size < 5:
            return False
        blocks = min(self.data[3] + 1, (self.size + 255) // 256)
        for block in range(blocks):
            size = self.displayid_block_size(block)
            if size >= 5 and not self.is_valid_checksum(block * DISPLAYID_BLOCK_SIZE, size):
                return False
        return True

    def is_valid_checksum(self, offset: int, size: int, add: int = 0) -> bool:
        if offset < 0 or size < 1:
            return False
        block = self.data[offset : offset + size]
        if len(block) != size:
            return False
        return (sum(block) & 0xFF) == (add & 0xFF)

    def fix_edid_header(self) -> DisplayData:
        if self.size < EDID_BLOCK_SIZE:
            raise DisplayDataError("EDID header fix requires at least 128 bytes.")
        data = bytearray(self.data)
        data[:8] = EDID_HEADER
        return DisplayData(bytes(data), self.original_size)

    def fix_edid_extension_blocks(self) -> DisplayData:
        if self.size < EDID_BLOCK_SIZE:
            raise DisplayDataError("EDID extension fix requires at least 128 bytes.")
        data = bytearray(self.data)
        blocks = min(data[126] + 1, (len(data) + 127) // 128)
        for block in range(blocks - 1, 0, -1):
            offset = block * EDID_BLOCK_SIZE
            block_data = DisplayData(bytes(data)).data[offset : offset + EDID_BLOCK_SIZE]
            if len(block_data) < EDID_BLOCK_SIZE:
                del data[offset:]
                continue
            if not DisplayData(bytes(data)).is_valid_edid_extension_block(block):
                del data[offset : offset + EDID_BLOCK_SIZE]
        data[126] = max(0, len(data) // EDID_BLOCK_SIZE - 1)
        return DisplayData(bytes(data), self.original_size).fix_edid_checksums()

    def fix_edid_checksums(self) -> DisplayData:
        if self.size < EDID_BLOCK_SIZE:
            raise DisplayDataError("EDID checksum fix requires at least 128 bytes.")
        data = bytearray(self.data)
        blocks = min(data[126] + 1, len(data) // EDID_BLOCK_SIZE)
        for block in range(blocks):
            offset = block * EDID_BLOCK_SIZE
            data[offset + 127] = (-sum(data[offset : offset + 127])) & 0xFF
        return DisplayData(bytes(data), self.original_size)

    def fix_displayid_checksums(self) -> DisplayData:
        if self.size < 5:
            raise DisplayDataError("DisplayID checksum fix requires at least 5 bytes.")
        data = bytearray(self.data)
        blocks = min(data[3] + 1, (len(data) + 255) // 256)
        for block in range(blocks):
            offset = block * DISPLAYID_BLOCK_SIZE
            size = DisplayData(bytes(data)).displayid_block_size(block)
            if size >= 5:
                data[offset + size - 1] = (-sum(data[offset : offset + size - 1])) & 0xFF
        return DisplayData(bytes(data), self.original_size)

    def auto_fix(self) -> DisplayData:
        result = self
        if result.is_edid:
            if not result.has_valid_edid_header:
                result = result.fix_edid_header()
            if not result.has_valid_edid_extension_blocks():
                result = result.fix_edid_extension_blocks()
            if not result.has_valid_edid_checksums():
                result = result.fix_edid_checksums()
        elif result.is_displayid and not result.has_valid_displayid_checksums():
            result = result.fix_displayid_checksums()
        return result

    def product_id(self) -> str | None:
        if self.is_edid:
            return self._edid_product_id()
        if self.is_displayid:
            if self.data[0] < 0x20:
                return self._displayid_product_id(0x00) or self._displayid_product_id(0x20)
            return self._displayid_product_id(0x20) or self._displayid_product_id(0x00)
        return None

    def name(self) -> str | None:
        if self.is_edid:
            return self._edid_name(0xFC) or self._edid_name(0xFE)
        if self.is_displayid:
            if self.data[0] < 0x20:
                return self._displayid_name(0x00) or self._displayid_name(0x20)
            return self._displayid_name(0x20) or self._displayid_name(0x00)
        return None

    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.size < self.original_size:
            warnings.append(f"Input had {self.original_size} bytes; only {self.size} bytes are loaded.")
        if self.is_edid:
            if not self.has_valid_edid_header:
                warnings.append("EDID header is corrupted.")
            if not self.has_valid_edid_extension_blocks():
                warnings.append("One or more EDID extension blocks are invalid.")
            if not self.has_valid_edid_checksums():
                warnings.append("One or more EDID checksums are invalid.")
            if self.size < self.reported_size:
                warnings.append(f"EDID reports {self.reported_size} bytes but only {self.size} bytes are present.")
        elif self.is_displayid:
            if not self.has_valid_displayid_checksums():
                warnings.append("One or more DisplayID checksums are invalid.")
            if self.size < self.reported_size:
                warnings.append(f"DisplayID reports {self.reported_size} bytes but only {self.size} bytes are present.")
        else:
            warnings.append("Data is not recognized as valid EDID or DisplayID.")
        return warnings

    def summary_lines(self) -> list[str]:
        product_id = self.product_id() or "unknown"
        name = self.name() or "unknown"
        return [
            f"Type: {self.type_name}",
            f"Size: {self.size} bytes",
            f"Reported size: {self.reported_size} bytes",
            f"Product ID: {product_id}",
            f"Name: {name}",
        ]

    def to_text(self, columns: int = 16) -> str:
        items = [f"{byte:02X}" for byte in self.data]
        if columns <= 0:
            return " ".join(items) + "\r\n"
        lines = [" ".join(items[index : index + columns]) for index in range(0, len(items), columns)]
        return "\r\n".join(lines) + "\r\n"

    def to_dat(self) -> str:
        title = "EDID BYTES" if self.is_edid else "DISPLAYID BYTES" if self.is_displayid else "DATA BYTES"
        width = 4 if self.size > 256 else 2
        lines = [f"{title}:", "0x" + " " * width + "00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F"]
        lines.append(" " * (width + 2) + "------------------------------------------------")
        for offset in range(0, self.size, 16):
            chunk = " ".join(f"{byte:02X}" for byte in self.data[offset : offset + 16])
            lines.append(f"{offset:0{width}X} | {chunk}")
        return "\r\n".join(lines) + "\r\n"

    def to_inf(self) -> str:
        if not self.is_edid:
            raise DisplayDataError("INF export is only supported for EDID data.")
        blocks = self.edid_blocks(max_blocks=4)
        lines = [
            "; Generated by python_edid_tools",
            "[Version]",
            'Signature="$WINDOWS NT$"',
            "",
            "[Monitor_AddReg]",
        ]
        for index, block in enumerate(blocks):
            hex_bytes = ",".join(f"{byte:02X}" for byte in block)
            lines.append(f"HKR,EDID_OVERRIDE,{index},0x00000001,{hex_bytes}")
        return "\r\n".join(lines) + "\r\n"

    def edid_blocks(self, max_blocks: int = 8) -> list[bytes]:
        if not self.is_edid:
            raise DisplayDataError("EDID blocks require valid EDID data.")
        if self.size % EDID_BLOCK_SIZE != 0:
            raise DisplayDataError("EDID data size must be a multiple of 128 bytes.")
        reported_blocks = self.data[126] + 1
        available_blocks = self.size // EDID_BLOCK_SIZE
        if reported_blocks > available_blocks:
            raise DisplayDataError(
                f"EDID reports {reported_blocks} blocks but only {available_blocks} blocks are present."
            )
        if reported_blocks > max_blocks:
            raise DisplayDataError(f"EDID has {reported_blocks} blocks; this tool supports {max_blocks}.")
        return [
            self.data[index * EDID_BLOCK_SIZE : (index + 1) * EDID_BLOCK_SIZE]
            for index in range(reported_blocks)
        ]

    def _edid_product_id(self) -> str:
        manufacturer = "".join(
            chr(value)
            for value in (
                64 | ((self.data[8] >> 2) & 31),
                64 | ((self.data[8] << 3) & 24) | ((self.data[9] >> 5) & 7),
                64 | (self.data[9] & 31),
            )
        )
        product = f"{self.data[11]:02X}{self.data[10]:02X}"
        return manufacturer + product

    def _displayid_product_id(self, tag: int) -> str | None:
        end = self.displayid_block_size(0) - 1
        index = 6
        while index < end:
            offset = index - 2
            block = self.data[offset:]
            if len(block) >= 8 and block[0] == tag and block[2] >= 5:
                if tag == 0x00 and all(_is_graph(byte) for byte in block[3:6]):
                    prefix = bytes(block[3:6]).decode("latin1")
                else:
                    prefix = f"{block[3]:02X}{block[4]:02X}{block[5]:02X}"
                return prefix + f"{block[7]:02X}{block[6]:02X}"
            index += self.data[index] + 3
        return None

    def _edid_name(self, tag: int) -> str | None:
        if self.size < EDID_BLOCK_SIZE:
            return None
        for slot in range(4):
            offset = 54 + slot * 18
            descriptor = self.data[offset : offset + 18]
            if len(descriptor) != 18:
                continue
            if descriptor[:3] == b"\x00\x00\x00" and descriptor[3] == tag and descriptor[4] == 0:
                raw = descriptor[5:18].split(b"\x0A", 1)[0].split(b"\x00", 1)[0]
                return raw.decode("latin1", errors="replace").rstrip()
        return None

    def _displayid_name(self, tag: int) -> str | None:
        end = self.displayid_block_size(0) - 1
        index = 6
        while index < end:
            offset = index - 2
            block = self.data[offset:]
            if len(block) >= 15 and block[0] == tag and block[2] >= 12:
                size = min(block[14], block[2] - 12)
                raw = bytes(block[15 : 15 + size])
                return raw.decode("latin1", errors="replace").rstrip()
            index += self.data[index] + 3
        return None


def load_display_data(path: str | Path, *, trim: bool = True, max_size: int | None = 4096) -> DisplayData:
    raw = Path(path).read_bytes()
    parsed = _try_parse_text(raw)
    if parsed is None:
        data = raw
    else:
        data = parsed
    original_size = len(data)
    if max_size is not None and len(data) > max_size:
        data = data[:max_size]
    display_data = DisplayData(data, original_size)
    return display_data.trim_to_reported_size(max_size=max_size) if trim else display_data


def save_display_data(display_data: DisplayData, path: str | Path, output_format: str = "auto") -> None:
    target = Path(path)
    output_format = _resolve_format(target, output_format)
    if output_format == "bin":
        target.write_bytes(display_data.data)
    elif output_format == "txt":
        target.write_text(display_data.to_text(), encoding="ascii", newline="")
    elif output_format == "dat":
        target.write_text(display_data.to_dat(), encoding="ascii", newline="")
    elif output_format == "inf":
        target.write_text(display_data.to_inf(), encoding="ascii", newline="")
    else:
        raise DisplayDataError(f"Unsupported output format: {output_format}")


def _resolve_format(path: Path, output_format: str) -> str:
    if output_format != "auto":
        return output_format.lower()
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"bin", "txt", "dat", "inf"}:
        return suffix
    return "bin"


def _try_parse_text(raw: bytes) -> bytes | None:
    if b"\x00" in raw[:512]:
        from .cru_import_export import extract_first_edid_from_binary

        return extract_first_edid_from_binary(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        log_notice("UTF-8 text decode failed; trying latin1", error=exc)
        try:
            text = raw.decode("latin1")
        except UnicodeDecodeError as exc:
            log_notice("latin1 text decode failed", error=exc)
            return None

    for parser in (_parse_inf_text, _parse_dat_text, _parse_hex_text):
        parsed = parser(text)
        if parsed:
            return parsed
    return None


def _parse_dat_text(text: str) -> bytes | None:
    rows: list[int] = []
    saw_table = False
    expected_offset = 0
    for line in text.splitlines():
        if "|" not in line:
            continue
        left, right = line.split("|", 1)
        offset_match = re.search(r"\b([0-9A-Fa-f]{2,4})\s*$", left)
        if not offset_match:
            return None
        offset = int(offset_match.group(1), 16)
        if offset != expected_offset:
            return None
        tokens = re.findall(r"\b[0-9A-Fa-f]{2}\b", right)
        if not tokens:
            return None
        rows.extend(int(token, 16) for token in tokens)
        expected_offset += len(tokens)
        saw_table = True
    return bytes(rows) if saw_table else None


def _parse_inf_text(text: str) -> bytes | None:
    blocks: dict[int, bytes] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        tokens = [token for token in re.split(r'[\s,"]+', line) if token]
        if len(tokens) < 5:
            continue
        if tokens[0].upper() != "HKR" or tokens[1].upper() != "EDID_OVERRIDE":
            continue
        try:
            block = int(tokens[2], 0)
            flag = int(tokens[3], 0)
            data = bytes(int(token, 16) for token in tokens[4:132])
        except ValueError as exc:
            log_notice("INF EDID_OVERRIDE parse line skipped", error=exc, line=line)
            continue
        if flag != 1 or len(data) != EDID_BLOCK_SIZE:
            continue
        blocks[block] = data
    if not blocks or 0 not in blocks:
        return None
    highest = max(blocks)
    return b"".join(blocks.get(index, bytes(EDID_BLOCK_SIZE)) for index in range(highest + 1))


def _parse_hex_text(text: str) -> bytes | None:
    matches = re.findall(r"0[xX]([0-9A-Fa-f]{2})|\b([0-9A-Fa-f]{2})\b", text)
    if not matches:
        return None
    values = [first or second for first, second in matches]
    return bytes(int(value, 16) for value in values)


def _is_graph(value: int) -> bool:
    return 0x21 <= value <= 0x7E
