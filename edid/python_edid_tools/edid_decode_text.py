from __future__ import annotations

from math import gcd

from .edid_data import DisplayData
from .structured_edid import DetailedTiming, MonitorDescriptor, StructuredEDID


ESTABLISHED_DMT = {
    "640x480 @ 60 Hz": "DMT 0x04:   640x480    59.940476 Hz   4:3     31.469 kHz     25.175000 MHz",
    "800x600 @ 60 Hz": "DMT 0x09:   800x600    60.316541 Hz   4:3     37.879 kHz     40.000000 MHz",
    "1024x768 @ 60 Hz": "DMT 0x10:  1024x768    60.003840 Hz   4:3     48.363 kHz     65.000000 MHz",
}


STANDARD_DMT = {
    (1920, 1080, 60): "DMT 0x52:  1920x1080   60.000000 Hz  16:9     67.500 kHz    148.500000 MHz",
    (1680, 1050, 60): "DMT 0x3a:  1680x1050   59.954250 Hz  16:10    65.290 kHz    146.250000 MHz",
    (1280, 1024, 60): "DMT 0x23:  1280x1024   60.019740 Hz   5:4     63.981 kHz    108.000000 MHz",
    (1600, 900, 60): "DMT 0x53:  1600x900    60.000000 Hz  16:9     60.000 kHz    108.000000 MHz (RB)",
    (1440, 900, 60): "DMT 0x2f:  1440x900    59.887445 Hz  16:10    55.935 kHz    106.500000 MHz",
    (1280, 720, 60): "DMT 0x55:  1280x720    60.000000 Hz  16:9     45.000 kHz     74.250000 MHz",
}


def decode_display_data(display_data: DisplayData, *, include_hex: bool = True) -> str:
    if display_data.is_edid:
        return decode_edid(display_data, include_hex=include_hex)
    if display_data.is_displayid:
        from .displayid import DisplayIDDocument

        return "\n".join(DisplayIDDocument.parse(display_data).summary_lines())
    return "\n".join(display_data.summary_lines())


def decode_edid(display_data: DisplayData, *, include_hex: bool = True) -> str:
    structured = StructuredEDID.parse(display_data)
    base = display_data.data[:128]
    props = structured.properties
    failures: list[str] = []
    lines: list[str] = []
    if include_hex:
        lines.extend(["edid-decode (hex):", ""])
        lines.extend(_hex_lines(display_data.data))
        lines.extend(["", "----------------", ""])
    lines.append("Block 0, Base EDID:")
    lines.append(f"  EDID Structure Version & Revision: {props.edid_version[0]}.{props.edid_version[1]}")
    lines.extend(
        [
            "  Vendor & Product Identification:",
            f"    Manufacturer: {props.manufacturer_id}",
            f"    Model: {props.product_code}",
            f"    Serial Number: {props.serial_number}",
            f"    Made in: week {props.manufacture_week} of {props.manufacture_year}",
            "  Basic Display Parameters & Features:",
            "    Digital display" if props.digital_input else "    Analog display",
        ]
    )
    if props.digital_input:
        lines.append(f"    {_digital_interface_name(props.video_interface)}")
    else:
        syncs = []
        if props.separate_sync:
            syncs.append("Separate sync")
        if props.composite_sync:
            syncs.append("Composite sync")
        if props.sync_on_green:
            syncs.append("Sync on green")
        if syncs:
            lines.append(f"    {' '.join(syncs)}")
    lines.append(f"    Maximum image size: {props.width_cm} cm x {props.height_cm} cm")
    lines.append(f"    Gamma: {props.gamma:.2f}" if props.gamma else "    Gamma: undefined")
    dpms = []
    if props.standby:
        dpms.append("Standby")
    if props.suspend:
        dpms.append("Suspend")
    if props.active_off:
        dpms.append("Off")
    if dpms:
        lines.append(f"    DPMS levels: {' '.join(dpms)}")
    lines.append("    sRGB color space" if props.srgb else "    Undefined display color type")
    if props.preferred_timing:
        lines.append("    First detailed timing is the preferred timing")
    if props.continuous_frequency:
        lines.append("    Continuous frequency display")

    lines.extend(["  Color Characteristics:"])
    for label, key in (("Red  ", "red"), ("Green", "green"), ("Blue ", "blue"), ("White", "white")):
        x, y = props.chromaticity[key]
        lines.append(f"    {label}: {x:.4f}, {y:.4f}")

    lines.append("  Established Timings I & II:")
    established_lines = _established_lines(structured.established_timings)
    lines.extend(established_lines or ["    None"])

    lines.append("  Standard Timings:")
    standard_lines = []
    for timing in structured.standard_timings:
        if not timing.is_used:
            continue
        standard_lines.append("    " + STANDARD_DMT.get((timing.width, timing.height, timing.refresh_rate), _standard_line(timing)))
    lines.extend(standard_lines or ["    None"])

    lines.append("  Detailed Timing Descriptors:")
    for index, timing in enumerate(structured.detailed_timings, start=1):
        lines.extend(_dtd_lines(index, timing, indent="    "))
    for descriptor in structured.descriptors:
        lines.extend(_descriptor_lines(descriptor, failures))
    lines.append(f"Checksum: 0x{base[127]:02x}")

    preferred = structured.preferred_timing()
    if preferred:
        lines.extend(["", "----------------", "", "Preferred Video Timing if only Block 0 is parsed:"])
        lines.extend(_dtd_lines(1, preferred, indent="  DTD   "))
        lines.extend(["", "----------------", "", "Native Video Resolution:", f"  {preferred.h_active}x{preferred.v_active}"])

    for extension in structured.extensions:
        lines.extend(["", "----------------", "", f"Block {extension.index}, {extension.type_name}:"])
        if extension.tag == 0x02:
            lines.append(f"  Revision: {extension.revision}")
            lines.append(f"  Native detailed timings: {extension.flags & 0x0f}")
            lines.append(f"  Data blocks: {len(extension.data_blocks)}")
            for block in extension.data_blocks:
                lines.append(f"    {block.name}: {len(block.payload)} byte(s)")
            if extension.detailed_timings:
                lines.append("  Detailed timings:")
                for index, timing in enumerate(extension.detailed_timings, start=1):
                    lines.extend(_dtd_lines(index, timing, indent="    "))
        else:
            lines.append(f"  Raw extension bytes preserved: {len(extension.raw)}")

    lines.extend(["", "----------------", "", "Python EDID decoder"])
    if failures:
        lines.extend(["", "Failures:", "", "Block 0, Base EDID:"])
        lines.extend(f"  {failure}" for failure in failures)
        lines.extend(["", "EDID conformity: FAIL"])
    else:
        lines.extend(["", "EDID conformity: PASS"])
    return "\n".join(lines)


def _hex_lines(data: bytes) -> list[str]:
    return [" ".join(f"{byte:02x}" for byte in data[index : index + 16]) for index in range(0, len(data), 16)]


def _digital_interface_name(value: int | None) -> str:
    return {
        0: "Digital interface not defined",
        1: "DVI interface",
        2: "HDMI-a interface",
        3: "HDMI-b interface",
        4: "MDDI interface",
        5: "DisplayPort interface",
    }.get(value or 0, f"Digital interface code {value}")


def _established_lines(data: bytes) -> list[str]:
    from .resolutions import EstablishedTimingSet

    timing_set = EstablishedTimingSet(data)
    lines = []
    for name in timing_set.enabled():
        lines.append("    " + ESTABLISHED_DMT.get(name, name))
    return lines


def _standard_line(timing: object) -> str:
    aspect = f"{timing.aspect[0]}:{timing.aspect[1]}" if timing.aspect != (0, 0) else "unknown"
    return f"{timing.width}x{timing.height} @ {timing.refresh_rate} Hz {aspect}"


def _dtd_lines(index: int, timing: DetailedTiming, *, indent: str) -> list[str]:
    h_total = timing.h_active + timing.h_blanking
    v_total = timing.v_active + timing.v_blanking
    refresh = timing.refresh_rate or 0
    h_khz = timing.pixel_clock_khz / h_total if h_total else 0
    aspect = _aspect(timing.h_active, timing.v_active)
    h_back = timing.h_blanking - timing.h_sync_offset - timing.h_sync_width
    v_back = timing.v_blanking - timing.v_sync_offset - timing.v_sync_width
    return [
        f"{indent}{index}: {timing.h_active:5d}x{timing.v_active:<5d} {refresh:10.6f} Hz {aspect:>6s} {h_khz:10.3f} kHz {timing.pixel_clock_khz / 1000:13.6f} MHz ({timing.h_size_mm} mm x {timing.v_size_mm} mm)",
        f"{' ' * len(indent)}       Hfront {timing.h_sync_offset:4d} Hsync {timing.h_sync_width:3d} Hback {h_back:4d} Hpol {'P' if timing.positive_hsync else 'N'}",
        f"{' ' * len(indent)}       Vfront {timing.v_sync_offset:4d} Vsync {timing.v_sync_width:3d} Vback {v_back:4d} Vpol {'P' if timing.positive_vsync else 'N'}",
    ]


def _aspect(width: int, height: int) -> str:
    if not width or not height:
        return "?:?"
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _descriptor_lines(descriptor: MonitorDescriptor, failures: list[str]) -> list[str]:
    raw = descriptor.raw
    if descriptor.tag == 0xFD and len(raw) >= 18:
        min_v, max_v, min_h, max_h, max_clock = raw[5], raw[6], raw[7], raw[8], raw[9] * 10
        if raw[10] == 0x00:
            failures.append(f"Display Range Limits: Byte 11 is 0x{raw[10]:02x} instead of 0x0a.")
        if raw[11:18] != b" " * 7:
            failures.append("Display Range Limits: Bytes 12-17 must be 0x20.")
        return [
            "    Display Range Limits:",
            f"      Monitor ranges: {min_v}-{max_v} Hz V, {min_h}-{max_h} kHz H, max dotclock {max_clock} MHz",
        ]
    if descriptor.tag == 0xFC:
        return [f"    Display Product Name: '{descriptor.text or ''}'"]
    if descriptor.tag == 0xFF:
        return [f"    Display Serial Number: '{descriptor.text or ''}'"]
    if descriptor.tag == 0xFE:
        return [f"    Display Text: '{descriptor.text or ''}'"]
    if raw and raw != bytes(18):
        return [f"    {descriptor.name}: {raw.hex(' ')}"]
    return []
