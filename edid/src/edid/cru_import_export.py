from __future__ import annotations

from edid.edid_data import EDID_BLOCK_SIZE, EDID_HEADER, DisplayData


EMBEDDED_EDID_MAGIC = bytes([0x71, 0x42, 0x12, 0x83, 0x54, 0x24, 0x95, 0x66])
CRU_IMPORT_MAGIC = EMBEDDED_EDID_MAGIC


def extract_edids_from_binary(raw: bytes, *, max_blocks: int = 8) -> list[DisplayData]:
    """Scan arbitrary executable/resource data for embedded EDID-like payloads."""
    results: list[DisplayData] = []
    seen: set[bytes] = set()

    for start in _candidate_offsets(raw):
        for blocks in range(max_blocks, 0, -1):
            end = start + blocks * EDID_BLOCK_SIZE
            candidate = raw[start:end]
            if len(candidate) != blocks * EDID_BLOCK_SIZE:
                continue
            if candidate in seen:
                continue
            display_data = DisplayData(candidate).trim_to_reported_size(max_size=max_blocks * EDID_BLOCK_SIZE)
            if display_data.is_edid and display_data.has_valid_edid_checksums():
                seen.add(candidate)
                results.append(display_data)
                break

    return results


def extract_first_edid_from_binary(raw: bytes, *, max_blocks: int = 8) -> bytes | None:
    matches = extract_edids_from_binary(raw, max_blocks=max_blocks)
    return matches[0].data if matches else None


def _candidate_offsets(raw: bytes) -> list[int]:
    offsets: set[int] = set()
    cursor = 0
    while True:
        index = raw.find(EDID_HEADER, cursor)
        if index < 0:
            break
        offsets.add(index)
        cursor = index + 1

    cursor = 0
    while True:
        index = raw.find(EMBEDDED_EDID_MAGIC, cursor)
        if index < 0:
            break
        # Some import resources place the marker near the payload; scan the next small window.
        for offset in range(index, min(len(raw), index + 512)):
            if raw[offset : offset + len(EDID_HEADER)] == EDID_HEADER:
                offsets.add(offset)
        cursor = index + 1

    return sorted(offsets)
