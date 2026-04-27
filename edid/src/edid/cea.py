from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from edid.edid_data import DisplayDataError
from edid.structured_edid import CEADataBlock, CEADataBlockTag


HDMI_OUI = 0x000C03
HDMI_FORUM_OUI = 0xC45DD8
FREESYNC_OUI = 0x00001A

CEA_VIC_NAMES = {
    1: "640x480p @ 60 Hz 4:3",
    2: "720x480p @ 60 Hz 4:3",
    3: "720x480p @ 60 Hz 16:9",
    4: "1280x720p @ 60 Hz 16:9",
    5: "1920x1080i @ 60 Hz 16:9",
    16: "1920x1080p @ 60 Hz 16:9",
    31: "1920x1080p @ 50 Hz 16:9",
    32: "1920x1080p @ 24 Hz 16:9",
    93: "3840x2160p @ 24 Hz 16:9",
    94: "3840x2160p @ 25 Hz 16:9",
    95: "3840x2160p @ 30 Hz 16:9",
    97: "3840x2160p @ 60 Hz 16:9",
}


class AudioFormatCode(IntEnum):
    LPCM = 1
    AC3 = 2
    MPEG1 = 3
    MP3 = 4
    MPEG2 = 5
    AAC_LC = 6
    DTS = 7
    ATRAC = 8
    ONE_BIT_AUDIO = 9
    DD_PLUS = 10
    DTS_HD = 11
    MAT = 12
    DST = 13
    WMA_PRO = 14
    EXTENDED = 15


@dataclass
class ShortAudioDescriptor:
    format_code: int
    channels: int
    sample_rates: int
    detail: int

    @classmethod
    def parse(cls, data: bytes) -> ShortAudioDescriptor:
        if len(data) != 3:
            raise DisplayDataError("Short audio descriptors are 3 bytes.")
        return cls(format_code=(data[0] >> 3) & 0x0F, channels=(data[0] & 0x07) + 1, sample_rates=data[1], detail=data[2])

    def encode(self) -> bytes:
        return bytes([((self.format_code & 0x0F) << 3) | max(0, min(7, self.channels - 1)), self.sample_rates & 0x7F, self.detail & 0xFF])


@dataclass
class AudioDataBlock:
    descriptors: list[ShortAudioDescriptor]

    @classmethod
    def parse(cls, block: CEADataBlock) -> AudioDataBlock:
        return cls([ShortAudioDescriptor.parse(block.payload[index : index + 3]) for index in range(0, len(block.payload), 3) if len(block.payload[index : index + 3]) == 3])

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.AUDIO, b"".join(descriptor.encode() for descriptor in self.descriptors))


@dataclass
class VideoDataBlock:
    vic_codes: list[int]

    @classmethod
    def parse(cls, block: CEADataBlock) -> VideoDataBlock:
        return cls(list(block.payload))

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.VIDEO, bytes(self.vic_codes))

    def names(self) -> list[str]:
        return [CEA_VIC_NAMES.get(code & 0x7F, f"VIC {code & 0x7F}") for code in self.vic_codes]


@dataclass
class SpeakerAllocationBlock:
    flags: int

    @classmethod
    def parse(cls, block: CEADataBlock) -> SpeakerAllocationBlock:
        return cls(block.payload[0] if block.payload else 0)

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.SPEAKER_ALLOCATION, bytes([self.flags & 0xFF, 0x00, 0x00]))

    def set_stereo(self) -> None:
        self.flags = 0

    def set_5_1(self) -> None:
        self.flags = 0x0B

    def set_7_1(self) -> None:
        self.flags = 0x4F


@dataclass
class HDMISupportBlock:
    physical_address: tuple[int, int, int, int]
    deep_color_30: bool
    deep_color_36: bool
    deep_color_48: bool
    supports_ai: bool
    max_tmds_mhz: int | None
    raw_tail: bytes = b""

    @classmethod
    def parse(cls, block: CEADataBlock) -> HDMISupportBlock:
        payload = block.payload
        if len(payload) < 5 or block.oui != HDMI_OUI:
            raise DisplayDataError("Not an HDMI vendor-specific data block.")
        address = payload[3:5]
        flags = payload[6] if len(payload) > 6 else 0
        max_tmds = payload[7] * 5 if len(payload) > 7 and payload[7] else None
        return cls(
            physical_address=((address[0] >> 4) & 0x0F, address[0] & 0x0F, (address[1] >> 4) & 0x0F, address[1] & 0x0F),
            deep_color_30=bool(flags & 0x40),
            deep_color_36=bool(flags & 0x80),
            deep_color_48=bool(flags & 0x10),
            supports_ai=bool(flags & 0x80),
            max_tmds_mhz=max_tmds,
            raw_tail=payload[8:],
        )

    def to_block(self) -> CEADataBlock:
        a, b, c, d = self.physical_address
        payload = bytearray([0x03, 0x0C, 0x00, ((a & 0x0F) << 4) | (b & 0x0F), ((c & 0x0F) << 4) | (d & 0x0F), 0])
        flags = 0
        if self.deep_color_30:
            flags |= 0x40
        if self.deep_color_36:
            flags |= 0x80
        if self.deep_color_48:
            flags |= 0x10
        payload.append(flags)
        payload.append(0 if self.max_tmds_mhz is None else max(0, min(255, self.max_tmds_mhz // 5)))
        payload.extend(self.raw_tail)
        return CEADataBlock(CEADataBlockTag.VENDOR_SPECIFIC, bytes(payload))


@dataclass
class HDMIForumBlock:
    version: int
    max_frl_rate: int
    supports_dsc: bool
    raw_tail: bytes = b""

    @classmethod
    def parse(cls, block: CEADataBlock) -> HDMIForumBlock:
        if len(block.payload) < 6 or block.oui != HDMI_FORUM_OUI:
            raise DisplayDataError("Not an HDMI Forum data block.")
        return cls(version=block.payload[3], max_frl_rate=block.payload[5] & 0x0F, supports_dsc=bool(block.payload[5] & 0x80), raw_tail=block.payload[6:])

    def to_block(self) -> CEADataBlock:
        flags = (0x80 if self.supports_dsc else 0) | (self.max_frl_rate & 0x0F)
        return CEADataBlock(CEADataBlockTag.VENDOR_SPECIFIC, bytes([0xD8, 0x5D, 0xC4, self.version, 0, flags]) + self.raw_tail)


@dataclass
class HDRStaticMetadataBlock:
    eotf_flags: int
    descriptor_flags: int
    max_luminance: int | None = None
    max_frame_average_luminance: int | None = None
    min_luminance: int | None = None

    @classmethod
    def parse(cls, block: CEADataBlock) -> HDRStaticMetadataBlock:
        if block.extended_tag != 0x06 or len(block.payload) < 3:
            raise DisplayDataError("Not an HDR static metadata block.")
        values = list(block.payload[3:])
        return cls(block.payload[1], block.payload[2], *(values + [None, None, None])[:3])

    def to_block(self) -> CEADataBlock:
        payload = bytearray([0x06, self.eotf_flags & 0xFF, self.descriptor_flags & 0xFF])
        for value in (self.max_luminance, self.max_frame_average_luminance, self.min_luminance):
            if value is not None:
                payload.append(value & 0xFF)
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes(payload))


@dataclass
class ColorimetryBlock:
    flags: int
    metadata: int = 0

    @classmethod
    def parse(cls, block: CEADataBlock) -> ColorimetryBlock:
        if block.extended_tag != 0x05:
            raise DisplayDataError("Not a colorimetry block.")
        return cls(block.payload[1] if len(block.payload) > 1 else 0, block.payload[2] if len(block.payload) > 2 else 0)

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x05, self.flags & 0xFF, self.metadata & 0xFF]))


@dataclass
class VideoCapabilityBlock:
    flags: int

    @classmethod
    def parse(cls, block: CEADataBlock) -> VideoCapabilityBlock:
        if block.extended_tag != 0x00:
            raise DisplayDataError("Not a video capability block.")
        return cls(block.payload[1] if len(block.payload) > 1 else 0)

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x00, self.flags & 0xFF]))


@dataclass
class FreeSyncRangeBlock:
    minimum_hz: int
    maximum_hz: int
    raw: bytes = b""

    @classmethod
    def parse(cls, block: CEADataBlock) -> FreeSyncRangeBlock:
        if block.tag != CEADataBlockTag.VENDOR_SPECIFIC or len(block.payload) < 5:
            raise DisplayDataError("Not a FreeSync vendor block.")
        if block.oui not in {FREESYNC_OUI, 0x1A0000}:
            raise DisplayDataError("Vendor block OUI is not recognized as FreeSync.")
        return cls(block.payload[3], block.payload[4], block.payload[5:])

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.VENDOR_SPECIFIC, bytes([0x1A, 0x00, 0x00, self.minimum_hz & 0xFF, self.maximum_hz & 0xFF]) + self.raw)


@dataclass
class YCbCr420VideoBlock:
    vic_codes: list[int]

    @classmethod
    def parse(cls, block: CEADataBlock) -> YCbCr420VideoBlock:
        if block.extended_tag != 0x0E:
            raise DisplayDataError("Not a YCbCr 4:2:0 video data block.")
        return cls(list(block.payload[1:]))

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x0E]) + bytes(self.vic_codes))


@dataclass
class YCbCr420CapabilityMapBlock:
    bitmap: bytes

    @classmethod
    def parse(cls, block: CEADataBlock) -> YCbCr420CapabilityMapBlock:
        if block.extended_tag != 0x0F:
            raise DisplayDataError("Not a YCbCr 4:2:0 capability map.")
        return cls(block.payload[1:])

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x0F]) + self.bitmap)


@dataclass
class VideoFormatPreferenceBlock:
    preferred_codes: list[int]

    @classmethod
    def parse(cls, block: CEADataBlock) -> VideoFormatPreferenceBlock:
        if block.extended_tag != 0x0D:
            raise DisplayDataError("Not a video format preference block.")
        return cls(list(block.payload[1:]))

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x0D]) + bytes(self.preferred_codes))


@dataclass
class RoomConfigurationBlock:
    speaker_count: int
    flags: bytes

    @classmethod
    def parse(cls, block: CEADataBlock) -> RoomConfigurationBlock:
        if block.extended_tag != 0x13:
            raise DisplayDataError("Not a room configuration block.")
        return cls(block.payload[1] if len(block.payload) > 1 else 0, block.payload[2:])

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x13, self.speaker_count & 0xFF]) + self.flags)


@dataclass
class SpeakerLocationBlock:
    locations: bytes

    @classmethod
    def parse(cls, block: CEADataBlock) -> SpeakerLocationBlock:
        if block.extended_tag != 0x14:
            raise DisplayDataError("Not a speaker location block.")
        return cls(block.payload[1:])

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x14]) + self.locations)


@dataclass
class HDRDynamicMetadataBlock:
    metadata: bytes

    @classmethod
    def parse(cls, block: CEADataBlock) -> HDRDynamicMetadataBlock:
        if block.extended_tag != 0x07:
            raise DisplayDataError("Not an HDR dynamic metadata block.")
        return cls(block.payload[1:])

    def to_block(self) -> CEADataBlock:
        return CEADataBlock(CEADataBlockTag.EXTENDED, bytes([0x07]) + self.metadata)


@dataclass
class TiledDisplayTopologyBlock:
    raw: bytes

    @classmethod
    def parse(cls, block: CEADataBlock) -> TiledDisplayTopologyBlock:
        # Preserve every byte because vendor topology variants differ.
        if block.extended_tag not in {0x12, 0x20} and block.tag != CEADataBlockTag.VENDOR_SPECIFIC:
            raise DisplayDataError("Not a tiled/topology-capable CEA block.")
        return cls(block.payload)

    def to_block(self) -> CEADataBlock:
        tag = CEADataBlockTag.EXTENDED if self.raw and self.raw[0] in {0x12, 0x20} else CEADataBlockTag.VENDOR_SPECIFIC
        return CEADataBlock(tag, self.raw)


def cea_payload_bytes(blocks: list[CEADataBlock]) -> int:
    return sum(1 + len(block.payload) for block in blocks)


def cea_bytes_left(blocks: list[CEADataBlock], *, dtd_bytes: int = 0) -> int:
    return 123 - cea_payload_bytes(blocks) - dtd_bytes


def validate_cea_budget(blocks: list[CEADataBlock], *, dtd_bytes: int = 0) -> None:
    remaining = cea_bytes_left(blocks, dtd_bytes=dtd_bytes)
    if remaining < 0:
        raise DisplayDataError(f"CEA extension exceeds available space by {-remaining} bytes.")


def classify_cea_block(block: CEADataBlock) -> object:
    if block.tag == CEADataBlockTag.AUDIO:
        return AudioDataBlock.parse(block)
    if block.tag == CEADataBlockTag.VIDEO:
        return VideoDataBlock.parse(block)
    if block.tag == CEADataBlockTag.SPEAKER_ALLOCATION:
        return SpeakerAllocationBlock.parse(block)
    if block.tag == CEADataBlockTag.VENDOR_SPECIFIC and block.oui == HDMI_OUI:
        return HDMISupportBlock.parse(block)
    if block.tag == CEADataBlockTag.VENDOR_SPECIFIC and block.oui == HDMI_FORUM_OUI:
        return HDMIForumBlock.parse(block)
    if block.extended_tag == 0x06:
        return HDRStaticMetadataBlock.parse(block)
    if block.extended_tag == 0x05:
        return ColorimetryBlock.parse(block)
    if block.extended_tag == 0x00:
        return VideoCapabilityBlock.parse(block)
    if block.extended_tag == 0x0E:
        return YCbCr420VideoBlock.parse(block)
    if block.extended_tag == 0x0F:
        return YCbCr420CapabilityMapBlock.parse(block)
    if block.extended_tag == 0x0D:
        return VideoFormatPreferenceBlock.parse(block)
    if block.extended_tag == 0x13:
        return RoomConfigurationBlock.parse(block)
    if block.extended_tag == 0x14:
        return SpeakerLocationBlock.parse(block)
    if block.extended_tag == 0x07:
        return HDRDynamicMetadataBlock.parse(block)
    return block
