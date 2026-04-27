from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from edid.structured_edid import MonitorDescriptor, StructuredEDID


@dataclass(slots=True)
class CommonEdidFields:
    manufacturer_id: str
    product_code: int
    serial_number: int
    manufacture_week: int
    manufacture_year: int
    edid_version: int
    edid_revision: int
    width_cm: int
    height_cm: int
    gamma_byte: int


def apply_common_fields(raw: bytes, fields: CommonEdidFields) -> bytes:
    updated = bytearray(raw)
    updated[8:10] = encode_manufacturer_id(fields.manufacturer_id)
    updated[10:12] = fields.product_code.to_bytes(2, "little")
    updated[12:16] = (fields.serial_number & 0xFFFFFFFF).to_bytes(4, "little")
    updated[16] = fields.manufacture_week
    updated[17] = fields.manufacture_year - 1990
    updated[18] = fields.edid_version
    updated[19] = fields.edid_revision
    updated[21] = fields.width_cm
    updated[22] = fields.height_cm
    updated[23] = 0xFF if fields.gamma_byte == 0 else fields.gamma_byte
    return bytes(updated)


def apply_digital_input(raw: bytes, bit_depth_code: int, interface_code: int) -> bytes:
    updated = bytearray(raw)
    updated[20] = 0x80 | ((bit_depth_code & 0x07) << 4) | (interface_code & 0x0F)
    return bytes(updated)


def apply_analog_input(raw: bytes, analog_level_code: int, separate_sync: bool, composite_sync: bool, sync_on_green: bool) -> bytes:
    updated = bytearray(raw)
    updated[20] = (
        ((analog_level_code & 0x03) << 5)
        | (0x08 if separate_sync else 0)
        | (0x04 if composite_sync else 0)
        | (0x02 if sync_on_green else 0)
    )
    return bytes(updated)


def apply_feature_flags(raw: bytes, flags: Iterable[tuple[int, bool]]) -> bytes:
    updated = bytearray(raw)
    features = updated[24]
    for mask, enabled in flags:
        features = set_bit(features, mask, enabled)
    updated[24] = features
    return bytes(updated)


def apply_color_bytes(raw: bytes, values: Iterable[int]) -> bytes:
    updated = bytearray(raw)
    for offset, value in zip(range(25, 35), values):
        updated[offset] = value
    return bytes(updated)


def set_text_descriptor(structured: StructuredEDID, tag: int, text: str) -> None:
    if not text:
        structured.set_descriptor_enabled(tag, False)
        return
    for descriptor in structured.descriptors:
        if descriptor.tag == tag:
            descriptor.text = text
            return
    _store_descriptor(structured, MonitorDescriptor(tag=tag, text=text, raw=b""))


def set_range_descriptor(structured: StructuredEDID, min_v: int, max_v: int, min_h: int, max_h: int, max_clock_mhz: int) -> None:
    if not any((min_v, max_v, min_h, max_h, max_clock_mhz)):
        structured.set_descriptor_enabled(0xFD, False)
        return
    payload = bytearray(b"\x00\x00\x00\xFD\x00" + bytes(13))
    payload[5] = min_v
    payload[6] = max_v
    payload[7] = min_h
    payload[8] = max_h
    payload[9] = min(255, max_clock_mhz // 10)
    payload[10] = 0x0A
    payload[11:18] = b" " * 7
    for descriptor in structured.descriptors:
        if descriptor.tag == 0xFD:
            descriptor.raw = bytes(payload)
            descriptor.text = None
            return
    _store_descriptor(structured, MonitorDescriptor(tag=0xFD, text=None, raw=bytes(payload)))


def _store_descriptor(structured: StructuredEDID, descriptor: MonitorDescriptor) -> None:
    for index, existing in enumerate(structured.descriptors):
        if existing.tag == descriptor.tag:
            structured.descriptors[index] = descriptor
            return
    for index, existing in enumerate(structured.descriptors):
        if existing.tag == 0 and (not existing.raw or existing.raw == bytes(18)):
            structured.descriptors[index] = descriptor
            return
    structured.descriptors.append(descriptor)


def depth_code(bit_depth: int | None) -> int:
    return {6: 1, 8: 2, 10: 3, 12: 4, 14: 5, 16: 6}.get(bit_depth or 0, 0)


def encode_manufacturer_id(value: str) -> bytes:
    text = (value.upper() + "   ")[:3]
    values = [max(1, min(26, ord(char) - 64)) for char in text]
    packed = (values[0] << 10) | (values[1] << 5) | values[2]
    return packed.to_bytes(2, "big")


def descriptor_text(structured: StructuredEDID, tag: int) -> str:
    for descriptor in structured.descriptors:
        if descriptor.tag == tag:
            return descriptor.text or ""
    return ""


def set_bit(value: int, mask: int, enabled: bool) -> int:
    return (value | mask) if enabled else (value & ~mask)
