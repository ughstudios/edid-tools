import tempfile
import unittest
from pathlib import Path
import os

from python_edid_tools.cea import (
    AudioDataBlock,
    HDRDynamicMetadataBlock,
    HDRStaticMetadataBlock,
    ShortAudioDescriptor,
    VideoFormatPreferenceBlock,
    YCbCr420CapabilityMapBlock,
    YCbCr420VideoBlock,
    cea_bytes_left,
)
from python_edid_tools.cru_import_export import CRU_IMPORT_MAGIC, extract_first_edid_from_binary
from python_edid_tools.displayid import DisplayIDContainerID, DisplayIDDataBlock, DisplayIDDocument, DisplayIDTimingBlock
from python_edid_tools.edid_data import DisplayData, load_display_data, save_display_data
from python_edid_tools.edid_decode_text import decode_edid
from python_edid_tools.hardware_display import make_mock_hardware_display
from python_edid_tools.list_model import EditableList
from python_edid_tools.resolutions import EstablishedTimingSet, TimingMode, make_timing
from python_edid_tools.structured_edid import CEADataBlock, DetailedTiming, StructuredEDID


TMP_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"


def make_sample_edid() -> bytes:
    data = bytearray(128)
    data[:8] = b"\x00\xFF\xFF\xFF\xFF\xFF\xFF\x00"
    data[8:12] = bytes([0x0E, 0x55, 0x34, 0x12])
    data[18] = 1
    data[19] = 3
    data[54:72] = b"\x00\x00\x00\xFC\x00Toasty!\n     "
    data[126] = 0
    data[127] = (-sum(data[:127])) & 0xFF
    return bytes(data)


SAMPLE_EDID = make_sample_edid()


def workspace_tempdir() -> tempfile.TemporaryDirectory[str]:
    TMP_ROOT.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TMP_ROOT)


class DisplayDataTests(unittest.TestCase):
    def test_sample_edid_summary(self) -> None:
        data = DisplayData(SAMPLE_EDID)

        self.assertTrue(data.is_edid)
        self.assertEqual(data.product_id(), "CRU1234")
        self.assertEqual(data.name(), "Toasty!")
        self.assertTrue(data.has_valid_edid_checksums())

    def test_checksum_repair(self) -> None:
        broken = bytearray(SAMPLE_EDID)
        broken[54] ^= 0x01
        data = DisplayData(bytes(broken))

        self.assertFalse(data.has_valid_edid_checksums())
        fixed = data.fix_edid_checksums()
        self.assertTrue(fixed.has_valid_edid_checksums())

    def test_dat_roundtrip(self) -> None:
        data = DisplayData(SAMPLE_EDID)
        with workspace_tempdir() as directory:
            path = Path(directory) / "sample.dat"
            save_display_data(data, path, "dat")
            loaded = load_display_data(path)

        self.assertEqual(loaded.data, SAMPLE_EDID)

    def test_txt_roundtrip(self) -> None:
        data = DisplayData(SAMPLE_EDID)
        with workspace_tempdir() as directory:
            path = Path(directory) / "sample.txt"
            save_display_data(data, path, "txt")
            loaded = load_display_data(path)

        self.assertEqual(loaded.data, SAMPLE_EDID)

    def test_structured_base_summary(self) -> None:
        structured = StructuredEDID.parse(DisplayData(SAMPLE_EDID))

        self.assertEqual(structured.properties.manufacturer_id, "CRU")
        self.assertEqual(structured.properties.product_code, 0x1234)
        self.assertEqual(structured.properties.name, "Toasty!")
        self.assertEqual(structured.summary_lines()[0], "Manufacturer/Product: CRU1234")

    def test_edid_decode_text_contains_full_sections(self) -> None:
        decoded = decode_edid(DisplayData(SAMPLE_EDID))

        self.assertIn("Block 0, Base EDID:", decoded)
        self.assertIn("Vendor & Product Identification:", decoded)
        self.assertIn("Detailed Timing Descriptors:", decoded)
        self.assertIn("EDID conformity:", decoded)

    def test_structured_cea_data_block_roundtrip(self) -> None:
        base = bytearray(SAMPLE_EDID)
        base[126] = 1
        base[127] = (-sum(base[:127])) & 0xFF
        cea = bytearray(128)
        cea[0] = 0x02
        cea[1] = 0x03
        cea[2] = 8
        cea[3] = 0
        cea[4] = (2 << 5) | 3
        cea[5:8] = bytes([16, 31, 4])
        cea[127] = (-sum(cea[:127])) & 0xFF

        structured = StructuredEDID.parse(DisplayData(bytes(base + cea)))
        self.assertEqual(structured.extensions[0].type_name, "CEA-861")
        self.assertEqual(structured.extensions[0].data_blocks[0].name, "Video")

        structured.extensions[0].data_blocks.append(CEADataBlock(tag=4, payload=b"\x01\x00\x00"))
        encoded = structured.encode()
        reparsed = StructuredEDID.parse(encoded)

        self.assertTrue(encoded.has_valid_edid_checksums())
        self.assertEqual([block.name for block in reparsed.extensions[0].data_blocks], ["Video", "Speaker Allocation"])

    def test_established_timing_set(self) -> None:
        timings = EstablishedTimingSet(b"\x00\x00\x00").set_enabled("1024x768 @ 60 Hz", True)

        self.assertTrue(timings.is_enabled("1024x768 @ 60 Hz"))
        self.assertIn("1024x768 @ 60 Hz", timings.enabled())

    def test_timing_generation(self) -> None:
        timing = make_timing(1920, 1080, 60, TimingMode.CVT_RB)

        self.assertEqual(timing.width, 1920)
        self.assertEqual(timing.height, 1080)
        self.assertGreater(timing.pixel_clock_khz, 0)
        self.assertGreater(timing.h_total, timing.width)

    def test_structured_edid_reencodes_detailed_and_descriptors(self) -> None:
        structured = StructuredEDID.parse(DisplayData(SAMPLE_EDID))
        structured.detailed_timings.append(
            DetailedTiming(
                pixel_clock_khz=148500,
                h_active=1920,
                h_blanking=280,
                v_active=1080,
                v_blanking=45,
                h_sync_offset=88,
                h_sync_width=44,
                v_sync_offset=4,
                v_sync_width=5,
                h_size_mm=0,
                v_size_mm=0,
                h_border=0,
                v_border=0,
                interlaced=False,
                stereo=0,
                sync_type=3,
                positive_hsync=True,
                positive_vsync=True,
                raw=b"",
            )
        )
        structured.set_preferred_timing(0)
        structured.set_descriptor_enabled(0xFC, False)

        encoded = structured.encode()
        reparsed = StructuredEDID.parse(encoded)

        self.assertEqual(reparsed.detailed_timings[0].h_active, 1920)
        self.assertIsNone(reparsed.properties.name)
        self.assertTrue(encoded.has_valid_edid_checksums())

    def test_audio_and_hdr_blocks(self) -> None:
        audio = AudioDataBlock([ShortAudioDescriptor(format_code=1, channels=2, sample_rates=0x7F, detail=0x07)])
        parsed_audio = AudioDataBlock.parse(audio.to_block())
        hdr = HDRStaticMetadataBlock(eotf_flags=0x05, descriptor_flags=0x01, max_luminance=100)
        parsed_hdr = HDRStaticMetadataBlock.parse(hdr.to_block())

        self.assertEqual(parsed_audio.descriptors[0].channels, 2)
        self.assertEqual(parsed_hdr.max_luminance, 100)

    def test_displayid_document_roundtrip(self) -> None:
        document = DisplayIDDocument(
            version=0x20,
            revision=0,
            product_type=0,
            extension_count=0,
            blocks=[DisplayIDDataBlock(tag=0x0B, revision=0, payload=b"Toasty Display\x00")],
        )

        encoded = document.encode()
        parsed = DisplayIDDocument.parse(encoded)

        self.assertTrue(encoded.is_displayid)
        self.assertTrue(encoded.has_valid_displayid_checksums())
        self.assertEqual(parsed.blocks[0].name, "General Purpose ASCII String")

    def test_editable_list_operations(self) -> None:
        items = EditableList[int]([1, 2])
        items.add(3)
        items.move_up(2)
        items.copy(1)
        items.paste()

        self.assertEqual(items.items, [1, 3, 2, 3])
        self.assertTrue(items.undo())
        self.assertEqual(items.items, [1, 3, 2])

    def test_mock_hardware_write_and_verify(self) -> None:
        display = make_mock_hardware_display(SAMPLE_EDID)
        updated = bytearray(SAMPLE_EDID)
        updated[21] = 52
        updated[127] = (-sum(updated[:127])) & 0xFF
        display.write_and_verify_edid(DisplayData(bytes(updated)))

        self.assertEqual(display.read_edid().data, bytes(updated))

    def test_cru_binary_import_scan(self) -> None:
        raw = b"stub" + CRU_IMPORT_MAGIC + b"padding" + SAMPLE_EDID + b"trailer"

        self.assertEqual(extract_first_edid_from_binary(raw), SAMPLE_EDID)

    def test_load_embedded_binary_edid(self) -> None:
        with workspace_tempdir() as directory:
            path = Path(directory) / "embedded.exe"
            path.write_bytes(b"stub\x00" + CRU_IMPORT_MAGIC + b"padding" + SAMPLE_EDID)
            loaded = load_display_data(path)

        self.assertEqual(loaded.data, SAMPLE_EDID)

    def test_cea_extended_blocks_and_budget(self) -> None:
        y420 = YCbCr420VideoBlock([97, 102]).to_block()
        cap = YCbCr420CapabilityMapBlock(b"\x03").to_block()
        preference = VideoFormatPreferenceBlock([16, 4]).to_block()
        dynamic = HDRDynamicMetadataBlock(b"\x01\x02").to_block()

        self.assertEqual(YCbCr420VideoBlock.parse(y420).vic_codes, [97, 102])
        self.assertEqual(YCbCr420CapabilityMapBlock.parse(cap).bitmap, b"\x03")
        self.assertEqual(VideoFormatPreferenceBlock.parse(preference).preferred_codes, [16, 4])
        self.assertEqual(HDRDynamicMetadataBlock.parse(dynamic).metadata, b"\x01\x02")
        self.assertGreater(cea_bytes_left([y420, cap, preference, dynamic]), 0)

    def test_displayid_timing_and_container_blocks(self) -> None:
        timing = DisplayIDDataBlock(0x22, 0, bytes(range(20)))
        container = DisplayIDDataBlock(0x29, 0, bytes(range(16)))
        document = DisplayIDDocument(0x20, 0, 0, 0, [timing, container])
        parsed = DisplayIDDocument.parse(document.encode())
        typed = parsed.typed_blocks()

        self.assertIsInstance(typed[0], DisplayIDTimingBlock)
        self.assertIsInstance(typed[1], DisplayIDContainerID)
        self.assertEqual(typed[1].hex, bytes(range(16)).hex())

    def test_typed_editor_smoke(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from python_edid_tools.gui_editors import TypedEditorDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = TypedEditorDialog(DisplayData(SAMPLE_EDID))

        self.assertIsNotNone(app)
        self.assertEqual(dialog.windowTitle(), "Advanced EDID Editors")

    def test_basic_edid_wizard_factory(self) -> None:
        from python_edid_tools.gui import _create_basic_edid

        data = _create_basic_edid(
            name="Wizard Panel",
            manufacturer="CLT",
            product_code=0x1234,
            serial=123,
            width_cm=60,
            height_cm=34,
            h_active=1920,
            v_active=1080,
            refresh=60,
            timing_mode="cvt_rb",
        )

        self.assertTrue(data.is_edid)
        self.assertEqual(data.name(), "Wizard Panel")
        self.assertTrue(data.has_valid_edid_checksums())


if __name__ == "__main__":
    unittest.main()
