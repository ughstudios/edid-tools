from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


ESTABLISHED_TIMINGS = [
    ("720x400 @ 70 Hz", 0, 7),
    ("720x400 @ 88 Hz", 0, 6),
    ("640x480 @ 60 Hz", 0, 5),
    ("640x480 @ 67 Hz", 0, 4),
    ("640x480 @ 72 Hz", 0, 3),
    ("640x480 @ 75 Hz", 0, 2),
    ("800x600 @ 56 Hz", 0, 1),
    ("800x600 @ 60 Hz", 0, 0),
    ("800x600 @ 72 Hz", 1, 7),
    ("800x600 @ 75 Hz", 1, 6),
    ("832x624 @ 75 Hz", 1, 5),
    ("1024x768 @ 87 Hz interlaced", 1, 4),
    ("1024x768 @ 60 Hz", 1, 3),
    ("1024x768 @ 70 Hz", 1, 2),
    ("1024x768 @ 75 Hz", 1, 1),
    ("1280x1024 @ 75 Hz", 1, 0),
    ("1152x870 @ 75 Hz", 2, 7),
]


class TimingMode(str, Enum):
    MANUAL = "manual"
    AUTOMATIC_PC = "automatic_pc"
    AUTOMATIC_HDTV = "automatic_hdtv"
    AUTOMATIC_CRT = "automatic_crt"
    EXACT = "exact"
    NATIVE = "native"
    CVT = "cvt"
    CVT_RB = "cvt_rb"
    CVT_RB2 = "cvt_rb2"
    GTF = "gtf"


@dataclass
class EstablishedTimingSet:
    data: bytes

    def __post_init__(self) -> None:
        self.data = bytes(self.data[:3]).ljust(3, b"\x00")

    def enabled(self) -> list[str]:
        return [name for name, byte, bit in ESTABLISHED_TIMINGS if self.data[byte] & (1 << bit)]

    def is_enabled(self, name: str) -> bool:
        for timing_name, byte, bit in ESTABLISHED_TIMINGS:
            if timing_name == name:
                return bool(self.data[byte] & (1 << bit))
        raise KeyError(name)

    def set_enabled(self, name: str, enabled: bool) -> EstablishedTimingSet:
        data = bytearray(self.data)
        for timing_name, byte, bit in ESTABLISHED_TIMINGS:
            if timing_name == name:
                if enabled:
                    data[byte] |= 1 << bit
                else:
                    data[byte] &= ~(1 << bit)
                return EstablishedTimingSet(bytes(data))
        raise KeyError(name)


@dataclass
class TimingParameters:
    width: int
    height: int
    refresh_hz: float
    pixel_clock_khz: int
    h_front_porch: int
    h_sync_width: int
    h_back_porch: int
    v_front_porch: int
    v_sync_width: int
    v_back_porch: int
    h_sync_positive: bool = True
    v_sync_positive: bool = True
    interlaced: bool = False

    @property
    def h_blanking(self) -> int:
        return self.h_front_porch + self.h_sync_width + self.h_back_porch

    @property
    def v_blanking(self) -> int:
        return self.v_front_porch + self.v_sync_width + self.v_back_porch

    @property
    def h_total(self) -> int:
        return self.width + self.h_blanking

    @property
    def v_total(self) -> int:
        return self.height + self.v_blanking


def make_timing(width: int, height: int, refresh_hz: float, mode: TimingMode = TimingMode.CVT_RB) -> TimingParameters:
    if mode in {TimingMode.CVT_RB, TimingMode.CVT_RB2, TimingMode.AUTOMATIC_PC, TimingMode.NATIVE}:
        return cvt_reduced_blanking(width, height, refresh_hz, rb2=mode == TimingMode.CVT_RB2)
    if mode in {TimingMode.CVT, TimingMode.AUTOMATIC_CRT}:
        return cvt(width, height, refresh_hz)
    if mode in {TimingMode.GTF, TimingMode.EXACT}:
        return gtf(width, height, refresh_hz)
    if mode == TimingMode.AUTOMATIC_HDTV:
        return hdtv_timing(width, height, refresh_hz)
    return cvt_reduced_blanking(width, height, refresh_hz)


def cvt_reduced_blanking(width: int, height: int, refresh_hz: float, *, rb2: bool = False) -> TimingParameters:
    h_blank = 160
    h_sync = 32
    h_front = 48
    h_back = h_blank - h_sync - h_front
    v_front = 8 if rb2 else 3
    v_sync = 8 if rb2 else 6
    v_back = 6 if rb2 else 26
    h_total = width + h_blank
    v_total = height + v_front + v_sync + v_back
    pixel_clock = _round_clock(h_total * v_total * refresh_hz / 1000)
    return TimingParameters(
        width,
        height,
        refresh_hz,
        pixel_clock,
        h_front,
        h_sync,
        h_back,
        v_front,
        v_sync,
        v_back,
        True,
        False,
    )


def cvt(width: int, height: int, refresh_hz: float) -> TimingParameters:
    h_blank = max(280, _round_to(width * 30 // 100, 8))
    h_sync = _round_to(h_blank * 8 // 100, 8)
    h_front = max(48, _round_to(h_blank // 3, 8))
    h_back = h_blank - h_sync - h_front
    v_front = 3
    v_sync = 5
    v_back = 36
    h_total = width + h_blank
    v_total = height + v_front + v_sync + v_back
    pixel_clock = _round_clock(h_total * v_total * refresh_hz / 1000)
    return TimingParameters(width, height, refresh_hz, pixel_clock, h_front, h_sync, h_back, v_front, v_sync, v_back)


def gtf(width: int, height: int, refresh_hz: float) -> TimingParameters:
    h_blank = _round_to(max(320, int(width * 0.35)), 8)
    h_sync = _round_to(h_blank * 8 // 100, 8)
    h_front = _round_to(h_blank // 4, 8)
    h_back = h_blank - h_sync - h_front
    v_front = 1
    v_sync = 3
    v_back = max(20, math.ceil(height * 0.03))
    h_total = width + h_blank
    v_total = height + v_front + v_sync + v_back
    pixel_clock = _round_clock(h_total * v_total * refresh_hz / 1000)
    return TimingParameters(width, height, refresh_hz, pixel_clock, h_front, h_sync, h_back, v_front, v_sync, v_back, True, True)


def hdtv_timing(width: int, height: int, refresh_hz: float) -> TimingParameters:
    known = {
        (1920, 1080): (88, 44, 148, 4, 5, 36),
        (1280, 720): (110, 40, 220, 5, 5, 20),
        (3840, 2160): (176, 88, 296, 8, 10, 72),
    }
    h_front, h_sync, h_back, v_front, v_sync, v_back = known.get(
        (width, height),
        (88, 44, 148, 4, 5, 36),
    )
    pixel_clock = _round_clock((width + h_front + h_sync + h_back) * (height + v_front + v_sync + v_back) * refresh_hz / 1000)
    return TimingParameters(width, height, refresh_hz, pixel_clock, h_front, h_sync, h_back, v_front, v_sync, v_back, True, True)


def _round_to(value: int, multiple: int) -> int:
    return int(round(value / multiple) * multiple)


def _round_clock(value_khz: float) -> int:
    return int(round(value_khz / 10) * 10)
