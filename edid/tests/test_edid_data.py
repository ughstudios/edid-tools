import shutil
import unittest
from pathlib import Path
import os
import re
from uuid import uuid4

from edid.cea import (
    AudioDataBlock,
    HDRDynamicMetadataBlock,
    HDRStaticMetadataBlock,
    ShortAudioDescriptor,
    VideoFormatPreferenceBlock,
    YCbCr420CapabilityMapBlock,
    YCbCr420VideoBlock,
    cea_bytes_left,
)
from edid.cru_import_export import CRU_IMPORT_MAGIC, extract_first_edid_from_binary
from edid.displayid import DisplayIDContainerID, DisplayIDDataBlock, DisplayIDDocument, DisplayIDTimingBlock
from edid.edid_data import DisplayData, load_display_data, save_display_data
from edid.edid_edit_service import CommonEdidFields, apply_common_fields, apply_digital_input, set_range_descriptor
from edid.edid_decode_text import decode_edid
from edid.edid_library import EdidLibrary, content_hash
from edid.hardware_display import make_mock_hardware_display
from edid.list_model import EditableList
from edid.resolutions import EstablishedTimingSet, TimingMode, make_timing
from edid.structured_edid import CEADataBlock, DetailedTiming, StructuredEDID


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


class WorkspaceTempDir:
    def __init__(self) -> None:
        self.path = TMP_ROOT / f"tmp-{uuid4().hex}"
        self.name = str(self.path)

    def __enter__(self) -> str:
        self.path.mkdir(parents=True, exist_ok=False)
        return self.name

    def __exit__(self, *_exc_info: object) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def workspace_tempdir() -> WorkspaceTempDir:
    TMP_ROOT.mkdir(exist_ok=True)
    return WorkspaceTempDir()


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

    def test_edid_library_import_rename_duplicate_delete(self) -> None:
        with workspace_tempdir() as directory:
            root = Path(directory) / "library"
            source = Path(directory) / "sample.bin"
            source.write_bytes(SAMPLE_EDID)
            library = EdidLibrary(root)

            imported = library.import_file(source)
            renamed = library.rename(imported.id, "Main Panel")
            duplicated = library.duplicate(renamed.id)
            library.delete(renamed.id)
            entries = library.list_entries()

            self.assertEqual(imported.name, "Toasty!")
            self.assertEqual(renamed.name, "Main Panel")
            self.assertEqual(library.load(duplicated.id).data, SAMPLE_EDID)
            self.assertEqual([entry.id for entry in entries], [duplicated.id])
            with self.assertRaises(KeyError):
                library.load(renamed.id)

    def test_edid_library_update_data_refreshes_metadata(self) -> None:
        updated_data = bytearray(SAMPLE_EDID)
        updated_data[54:72] = b"\x00\x00\x00\xFC\x00LibraryTwo   "
        updated_data[127] = (-sum(updated_data[:127])) & 0xFF
        with workspace_tempdir() as directory:
            library = EdidLibrary(Path(directory) / "library")
            entry = library.save_new(DisplayData(SAMPLE_EDID), name="Original")

            updated = library.update_data(entry.id, DisplayData(bytes(updated_data)), name="Updated")

            self.assertEqual(updated.name, "Updated")
            self.assertEqual(updated.display_name, "LibraryTwo")
            self.assertEqual(library.load(entry.id).data, bytes(updated_data))

    def test_edid_library_upserts_display_snapshots(self) -> None:
        changed_data = bytearray(SAMPLE_EDID)
        changed_data[21] = 61
        changed_data[127] = (-sum(changed_data[:127])) & 0xFF
        with workspace_tempdir() as directory:
            library = EdidLibrary(Path(directory) / "library")

            first = library.upsert_snapshot(
                DisplayData(SAMPLE_EDID),
                source_kind="display_active",
                display_key="DISPLAY\\ABC",
                device_id="DISPLAY",
                instance_id="ABC",
                source_label="Panel Active EDID",
            )
            repeated = library.upsert_snapshot(
                DisplayData(SAMPLE_EDID),
                source_kind="display_active",
                display_key="DISPLAY\\ABC",
                device_id="DISPLAY",
                instance_id="ABC",
                source_label="Panel Active EDID",
            )
            updated = library.upsert_snapshot(
                DisplayData(bytes(changed_data)),
                source_kind="display_active",
                display_key="DISPLAY\\ABC",
                device_id="DISPLAY",
                instance_id="ABC",
                source_label="Panel Active EDID",
            )
            override = library.upsert_snapshot(
                DisplayData(SAMPLE_EDID),
                source_kind="display_override",
                display_key="DISPLAY\\ABC",
                device_id="DISPLAY",
                instance_id="ABC",
                source_label="Panel Override EDID",
            )
            entries = library.list_entries()

            self.assertEqual(first.id, repeated.id)
            self.assertEqual(first.id, updated.id)
            self.assertNotEqual(updated.id, override.id)
            self.assertEqual(len(entries), 2)
            self.assertTrue(updated.auto_snapshot)
            self.assertEqual(updated.source_kind, "display_active")
            self.assertEqual(updated.display_key, "DISPLAY\\ABC")
            self.assertEqual(updated.content_hash, content_hash(DisplayData(bytes(changed_data))))
            self.assertEqual(library.load(updated.id).data, bytes(changed_data))

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

    def test_edid_decode_accepts_cvt_range_limits(self) -> None:
        data = bytearray(SAMPLE_EDID)
        data[19] = 4
        data[24] |= 0x01
        range_descriptor = bytearray(b"\x00\x00\x00\xFD\x00" + bytes(13))
        range_descriptor[5:10] = bytes([48, 144, 30, 167, 35])
        range_descriptor[10:18] = bytes([0x04, 0x13, 0x01, 0xE0, 0x40, 0x38, 0x00, 60])
        data[72:90] = range_descriptor
        data[127] = (-sum(data[:127])) & 0xFF

        decoded = decode_edid(DisplayData(bytes(data)), include_hex=False)

        self.assertIn("Display Range Limits:", decoded)
        self.assertNotIn("Bytes 12-17 must be 0x20", decoded)
        self.assertIn("EDID conformity: PASS", decoded)

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
            from edid.gui_editors import TypedEditorDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = TypedEditorDialog(DisplayData(SAMPLE_EDID))

        self.assertIsNotNone(app)
        self.assertEqual(dialog.windowTitle(), "Advanced EDID Editor")

    def test_typed_editor_applies_identity_fields(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.gui_editors import TypedEditorDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = TypedEditorDialog(DisplayData(SAMPLE_EDID))
        dialog._prop_manufacturer.setText("ABC")
        dialog._prop_product.setValue(0xBEEF)
        dialog._prop_week.setValue(7)
        dialog._prop_year.setValue(2024)
        dialog._prop_name.setText("RefactorTest")
        dialog._accept()

        parsed = StructuredEDID.parse(dialog.display_data)
        self.assertIsNotNone(app)
        self.assertEqual(parsed.properties.manufacturer_id, "ABC")
        self.assertEqual(parsed.properties.product_code, 0xBEEF)
        self.assertEqual(parsed.properties.manufacture_week, 7)
        self.assertEqual(parsed.properties.manufacture_year, 2024)
        self.assertEqual(parsed.properties.name, "RefactorTest")
        self.assertTrue(dialog.display_data.has_valid_edid_checksums())

    def test_edid_edit_service_common_fields(self) -> None:
        structured = StructuredEDID.parse(DisplayData(SAMPLE_EDID))
        raw = apply_common_fields(
            structured.raw,
            CommonEdidFields(
                manufacturer_id="ABC",
                product_code=0xBEEF,
                serial_number=999,
                manufacture_week=8,
                manufacture_year=2024,
                edid_version=1,
                edid_revision=4,
                width_cm=55,
                height_cm=31,
                gamma_byte=120,
            ),
        )
        raw = apply_digital_input(raw, bit_depth_code=2, interface_code=5)
        structured.raw = raw
        updated = structured.encode()

        reparsed = StructuredEDID.parse(updated)
        self.assertEqual(reparsed.properties.manufacturer_id, "ABC")
        self.assertEqual(reparsed.properties.product_code, 0xBEEF)
        self.assertEqual(reparsed.properties.manufacture_year, 2024)
        self.assertEqual(reparsed.properties.width_cm, 55)
        self.assertTrue(updated.has_valid_edid_checksums())

    def test_decoded_editor_applies_identity_and_range_fields(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.decoded_editor import DecodedEdidDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = DecodedEdidDialog(DisplayData(SAMPLE_EDID))
        dialog.manufacturer_edit.setText("XYZ")
        dialog.product_spin.setValue(0x4321)
        dialog.range_min_v.setValue(48)
        dialog.range_max_v.setValue(144)
        dialog.range_min_h.setValue(30)
        dialog.range_max_h.setValue(167)
        dialog.range_max_clock.setValue(340)
        dialog._accept()

        parsed = StructuredEDID.parse(dialog.display_data)
        self.assertIsNotNone(app)
        self.assertEqual(parsed.properties.manufacturer_id, "XYZ")
        self.assertEqual(parsed.properties.product_code, 0x4321)
        self.assertTrue(dialog.display_data.has_valid_edid_checksums())

    def test_workflow_editor_uses_guided_titles(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.gui_editors import WorkflowEditorDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = WorkflowEditorDialog(DisplayData(SAMPLE_EDID))
        self.assertIsNotNone(app)
        self.assertEqual(dialog.windowTitle(), "Professional EDID Editor (EDID payload)")
        tab_titles = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
        self.assertIn("Identity", tab_titles)
        self.assertIn("Range Limits", tab_titles)
        self.assertIn("Standard Modes", tab_titles)
        self.assertIn("Timings", tab_titles)
        self.assertIn("DisplayID", tab_titles)

    def test_workflow_editor_defaults_to_beginner_mode(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.gui_editors import WorkflowEditorDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = WorkflowEditorDialog(DisplayData(SAMPLE_EDID))
        toggle = dialog._ui.widgets["mode_toggle_button"]
        did_payload = dialog._ui.widgets["did_payload"]

        self.assertIsNotNone(app)
        self.assertEqual(toggle.text(), "Switch to Expert")
        self.assertTrue(did_payload.isHidden())

        toggle.click()
        self.assertEqual(toggle.text(), "Switch to Beginner")
        self.assertFalse(did_payload.isHidden())

    def test_workflow_displayid_tab_is_actionable_for_edid(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.gui_editors import WorkflowEditorDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = WorkflowEditorDialog(DisplayData(SAMPLE_EDID))
        displayid_list = dialog._ui.widgets["displayid_list"]

        self.assertIsNotNone(app)
        self.assertGreater(displayid_list.count(), 0)
        self.assertIn("No DisplayID", displayid_list.item(0).text())

    def test_typed_editor_applies_professional_fields(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.gui_editors import TypedEditorDialog
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        dialog = TypedEditorDialog(DisplayData(SAMPLE_EDID))
        analog_level = dialog._ui.widgets["prop_analog_level"]
        dialog._ui.widgets["prop_digital"].setChecked(False)
        analog_level.setCurrentIndex(analog_level.findData(2))
        dialog._ui.widgets["prop_separate_sync"].setChecked(True)
        dialog._ui.widgets["range_min_v"].setValue(48)
        dialog._ui.widgets["range_max_v"].setValue(144)
        dialog._ui.widgets["range_min_h"].setValue(30)
        dialog._ui.widgets["range_max_h"].setValue(160)
        dialog._ui.widgets["range_max_clock"].setValue(600)
        dialog._ui.widgets["standard_width"].setValue(1920)
        dialog._ui.widgets["standard_aspect"].setCurrentIndex(dialog._ui.widgets["standard_aspect"].findText("16:9"))
        dialog._ui.widgets["standard_refresh"].setValue(60)
        dialog._replace_standard_timing()
        dialog._accept()

        parsed = StructuredEDID.parse(dialog.display_data)
        self.assertIsNotNone(app)
        self.assertFalse(parsed.properties.digital_input)
        self.assertEqual(parsed.properties.analog_signal_level, 2)
        self.assertTrue(parsed.properties.separate_sync)
        self.assertIsNotNone(parsed.properties.range_limits)
        assert parsed.properties.range_limits is not None
        self.assertEqual(parsed.properties.range_limits[5], 48)
        self.assertEqual(parsed.standard_timings[0].width, 1920)
        self.assertEqual(parsed.standard_timings[0].height, 1080)
        self.assertTrue(dialog.display_data.has_valid_edid_checksums())

    def test_display_readback_snapshot_name_prefers_edid_name(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from edid.gui import MainWindow
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        name = MainWindow._snapshot_resolution_name(object(), DisplayData(SAMPLE_EDID), "active")

        self.assertEqual(name, "Toasty! (active)")

    def test_edid_edit_service_range_descriptor(self) -> None:
        structured = StructuredEDID.parse(DisplayData(SAMPLE_EDID))
        set_range_descriptor(structured, min_v=48, max_v=120, min_h=30, max_h=160, max_clock_mhz=300)
        descriptor = next((item for item in structured.descriptors if item.tag == 0xFD), None)
        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual(descriptor.raw[5], 48)
        self.assertEqual(descriptor.raw[6], 120)
        encoded = structured.encode()
        self.assertTrue(encoded.has_valid_edid_checksums())

    def test_basic_edid_wizard_factory(self) -> None:
        from edid.gui import _create_basic_edid

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

    def test_basic_edid_wizard_is_window_when_parented(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication, QWidget
            from edid.gui import EdidCreationWizard
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        parent = QWidget()
        wizard = EdidCreationWizard(parent)

        self.assertIsNotNone(app)
        self.assertIs(wizard.dialog.parent(), parent)
        self.assertTrue(wizard.dialog.isWindow())
        self.assertTrue(wizard.dialog.windowFlags() & Qt.WindowType.Dialog)

    def test_main_window_xml_has_library_tab_without_legacy_monitor_manager_name(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QMainWindow
            from edid.ui_factory import load_ui, xml_root_dir
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        app = QApplication.instance() or QApplication([])
        ui = load_ui(xml_root_dir() / "main_window.xml")
        tabs = ui["main_tabs"]
        tab_titles = [tabs.tabText(index) for index in range(tabs.count())]

        self.assertIsNotNone(app)
        self.assertIn("Library and live editor", tab_titles)
        self.assertNotIn("Monitor Manager", tab_titles)
        self.assertIn("manager_selected_combo", ui.widgets)
        self.assertIn("load_action", ui.widgets)
        self.assertIn("exit_action", ui.widgets)
        self.assertIn("preferences_action", ui.widgets)
        self.assertNotIn("edids_snapshot_button", ui.widgets)

        class Owner:
            def __init__(self) -> None:
                self.closed = False

            def _load_file(self) -> None:
                pass

            def _save_file(self) -> None:
                pass

            def _show_preferences(self) -> None:
                pass

            def _show_about(self) -> None:
                pass

            def close(self) -> None:
                self.closed = True

        owner = Owner()
        wired_ui = load_ui(xml_root_dir() / "main_window.xml", owner=owner, window=QMainWindow())
        wired_ui.widgets["exit_action"].trigger()
        self.assertTrue(owner.closed)

    def test_xml_on_clicked_callbacks_support_literals(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.ui_factory import load_ui
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        class Owner:
            def __init__(self) -> None:
                self.calls: list[tuple[str, int | None]] = []

            def clicked(self) -> None:
                self.calls.append(("clicked", None))

            def moved(self, direction: int) -> None:
                self.calls.append(("moved", direction))

        app = QApplication.instance() or QApplication([])
        owner = Owner()
        with workspace_tempdir() as directory:
            path = Path(directory) / "callbacks.xml"
            path.write_text(
                '<widget class="QWidget" name="root">'
                '<vbox name="layout">'
                '<QPushButton name="plain_button" text="Plain" on_clicked="clicked" />'
                '<QPushButton name="move_button" text="Move" on_clicked="moved(-1)" />'
                "</vbox>"
                "</widget>",
                encoding="utf-8",
            )
            ui = load_ui(path, owner=owner)

        self.assertIsNotNone(app)
        ui.widgets["plain_button"].click()
        ui.widgets["move_button"].click()
        self.assertEqual(owner.calls, [("clicked", None), ("moved", -1)])

    def test_xml_menu_actions_support_triggered_callbacks(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QMainWindow
            from edid.ui_factory import load_ui
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        class Owner:
            def __init__(self) -> None:
                self.triggered = False

            def run_action(self) -> None:
                self.triggered = True

        app = QApplication.instance() or QApplication([])
        window = QMainWindow()
        owner = Owner()
        with workspace_tempdir() as directory:
            path = Path(directory) / "menu.xml"
            path.write_text(
                '<widget class="QWidget" name="root">'
                '<menu_bar name="main_menu_bar">'
                '<menu name="file_menu" title="File">'
                '<action name="run_action" text="Run" on_triggered="run_action" />'
                "</menu>"
                "</menu_bar>"
                '<vbox name="layout" />'
                "</widget>",
                encoding="utf-8",
            )
            ui = load_ui(path, owner=owner, window=window)

        self.assertIsNotNone(app)
        self.assertIs(window.menuBar(), ui.widgets["main_menu_bar"])
        ui.widgets["run_action"].trigger()
        self.assertTrue(owner.triggered)

    def test_xml_callbacks_reject_unsafe_expressions(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from edid.ui_factory import UiFactoryError, load_ui
        except Exception as exc:
            self.skipTest(f"PySide6 unavailable: {exc}")

        class Owner:
            def clicked(self) -> None:
                pass

        app = QApplication.instance() or QApplication([])
        with workspace_tempdir() as directory:
            path = Path(directory) / "unsafe.xml"
            path.write_text(
                '<widget class="QWidget" name="root">'
                '<vbox name="layout">'
                '<QPushButton name="bad_button" text="Bad" on_clicked="__import__(\'os\').system(\'echo bad\')" />'
                "</vbox>"
                "</widget>",
                encoding="utf-8",
            )
            with self.assertRaises(UiFactoryError):
                load_ui(path, owner=Owner())

        self.assertIsNotNone(app)

    def test_ui_controllers_do_not_construct_widgets_directly(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "edid"
        forbidden = re.compile(
            r"\bQ(?:Widget|Dialog|PushButton|Label|VBoxLayout|HBoxLayout|GridLayout|FormLayout|GroupBox|"
            r"ComboBox|TextEdit|LineEdit|CheckBox|SpinBox|ListWidget|TabWidget|StackedWidget|"
            r"DialogButtonBox|ScrollArea|PlainTextEdit|StatusBar)\("
        )
        offenders: list[str] = []
        for relative in ("gui.py", "gui_editors.py", "decoded_editor.py"):
            text = (root / relative).read_text(encoding="utf-8")
            if forbidden.search(text):
                offenders.append(relative)

        self.assertEqual(offenders, [])

    def test_gui_uses_generated_ui_bindings_instead_of_ui_indexing(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "edid"
        text = (root / "gui.py").read_text(encoding="utf-8")

        self.assertNotRegex(text, r"\b[a-zA-Z_][a-zA-Z0-9_]*ui\s*\[")
        self.assertNotRegex(text, r"from edid\.ui\.[a-zA-Z0-9_]+ import \*")
        self.assertNotIn("load_ui(", text)
        self.assertNotIn("xml_root_dir", text)
        self.assertNotIn("load_mainwindow_widgets", text)
        self.assertNotIn("load_rawblockeditordialog_widgets", text)
        self.assertNotIn("load_edidcreationwizard_widgets", text)
        self.assertIn("MainwindowUi(owner=self, window=self)", text)
        self.assertIn("RawblockeditordialogUi()", text)
        self.assertIn("EdidcreationwizardUi()", text)

    def test_legacy_ui_trees_retired(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.assertFalse((project_root / "ui").exists())


if __name__ == "__main__":
    unittest.main()
