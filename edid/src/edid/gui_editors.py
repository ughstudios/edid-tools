from __future__ import annotations

import re

from edid.cea import (
    AudioDataBlock,
    ColorimetryBlock,
    FreeSyncRangeBlock,
    HDMIForumBlock,
    HDMISupportBlock,
    HDRStaticMetadataBlock,
    ShortAudioDescriptor,
    SpeakerAllocationBlock,
    VideoCapabilityBlock,
    VideoDataBlock,
    VideoFormatPreferenceBlock,
    YCbCr420VideoBlock,
)
from edid.displayid import DisplayIDDataBlock, DisplayIDDocument
from edid.edid_edit_service import (
    CommonEdidFields,
    apply_common_fields,
    apply_analog_input,
    apply_digital_input,
    apply_feature_flags,
    depth_code,
    descriptor_text,
    set_text_descriptor,
    set_range_descriptor,
)
from edid.edid_data import DisplayData, DisplayDataError
from edid.dialog_preferences import show_message
from edid.logging_utils import log_exception
from edid.resolutions import ESTABLISHED_TIMINGS, TimingMode, EstablishedTimingSet, make_timing
from edid.structured_edid import ASPECT_RATIOS, CEADataBlock, DetailedTiming, ExtensionBlock, StandardTiming, StructuredEDID
from edid.ui_factory import load_ui, xml_root_dir
from edid.ui.advancededideditordialog import *

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem, QMessageBox
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required for GUI editor mode. Install it with: pip install PySide6") from exc


class TypedEditorDialog:
    def __init__(self, display_data: DisplayData, parent: object | None = None) -> None:
        ui = bind_ui(load_ui(xml_root_dir() / "advanced_edid_editor_dialog.xml", owner=self))
        self._ui = ui
        self.dialog = ui.root
        self.dialog.resize(780, 560)
        self.dialog.setMinimumSize(640, 420)
        self.display_data = display_data
        self._structured = StructuredEDID.parse(display_data) if display_data.is_edid else None
        self._displayid = DisplayIDDocument.parse(display_data) if display_data.is_displayid else None
        if not self._structured and not self._displayid:
            raise DisplayDataError("Typed editors require EDID or DisplayID data.")
        self._bind(ui)

    def exec(self) -> int:
        return self.dialog.exec()

    def windowTitle(self) -> str:
        return self.dialog.windowTitle()

    def _bind(self, ui: AdvancededideditordialogUi) -> None:
        self.tabs = ui.advanced_tabs
        self._bind_properties(ui)
        self._bind_established(ui)
        self._bind_standard(ui)
        self._bind_detailed(ui)
        self._bind_cea(ui)
        self._bind_displayid(ui)
        button_box = ui.buttons
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.dialog.reject)
        if not self._structured:
            for name in ("properties_tab", "limits_tab", "established_tab", "standard_tab", "detailed_tab", "cea_tab"):
                self.tabs.setTabEnabled(self.tabs.indexOf(getattr(ui, name)), False)

    def _bind_properties(self, ui: AdvancededideditordialogUi) -> None:
        if not self._structured:
            return
        props = self._structured.properties
        self._prop_manufacturer = ui.prop_manufacturer
        self._prop_manufacturer.setMaxLength(3)
        self._prop_manufacturer.setText(props.manufacturer_id)
        self._prop_product = ui.prop_product
        self._prop_product.setValue(props.product_code)
        self._prop_serial_number = ui.prop_serial_number
        self._prop_serial_number.setText(str(props.serial_number))
        self._prop_week = ui.prop_week
        self._prop_week.setValue(props.manufacture_week)
        self._prop_year = ui.prop_year
        self._prop_year.setValue(props.manufacture_year)
        self._prop_version = ui.prop_version
        self._prop_version.setValue(props.edid_version[0])
        self._prop_revision = ui.prop_revision
        self._prop_revision.setValue(props.edid_version[1])
        self._prop_digital = ui.prop_digital
        self._prop_digital.setChecked(props.digital_input)
        self._prop_bit_depth = ui.prop_bit_depth
        for label, value in [("Undefined", 0), ("6 bpc", 1), ("8 bpc", 2), ("10 bpc", 3), ("12 bpc", 4), ("14 bpc", 5), ("16 bpc", 6)]:
            self._prop_bit_depth.addItem(label, value)
        self._prop_bit_depth.setCurrentIndex(max(0, self._prop_bit_depth.findData(depth_code(props.bit_depth))))
        self._prop_interface = ui.prop_interface
        for label, value in [("Undefined", 0), ("DVI", 1), ("HDMI-a", 2), ("HDMI-b", 3), ("MDDI", 4), ("DisplayPort", 5)]:
            self._prop_interface.addItem(label, value)
        self._prop_interface.setCurrentIndex(max(0, self._prop_interface.findData(props.video_interface or 0)))
        self._prop_analog_level = ui.prop_analog_level
        for label, value in [
            ("0.700 / 0.300 V", 0),
            ("0.714 / 0.286 V", 1),
            ("1.000 / 0.400 V", 2),
            ("0.700 / 0.000 V", 3),
        ]:
            self._prop_analog_level.addItem(label, value)
        self._prop_analog_level.setCurrentIndex(max(0, self._prop_analog_level.findData(props.analog_signal_level or 0)))
        self._prop_separate_sync = ui.prop_separate_sync
        self._prop_separate_sync.setChecked(props.separate_sync)
        self._prop_composite_sync = ui.prop_composite_sync
        self._prop_composite_sync.setChecked(props.composite_sync)
        self._prop_sync_on_green = ui.prop_sync_on_green
        self._prop_sync_on_green.setChecked(props.sync_on_green)
        self._prop_digital.toggled.connect(self._refresh_input_controls)
        self._prop_width = ui.prop_width
        self._prop_width.setValue(props.width_cm)
        self._prop_height = ui.prop_height
        self._prop_height.setValue(props.height_cm)
        self._prop_gamma = ui.prop_gamma
        self._prop_gamma.setValue(0 if props.gamma is None else round(props.gamma * 100 - 100))
        self._prop_srgb = ui.prop_srgb
        self._prop_srgb.setChecked(props.srgb)
        self._prop_preferred = ui.prop_preferred
        self._prop_preferred.setChecked(props.preferred_timing)
        self._prop_continuous = ui.prop_continuous
        self._prop_continuous.setChecked(props.continuous_frequency)
        self._prop_name = ui.prop_name
        self._prop_name.setMaxLength(13)
        self._prop_name.setText(props.name or "")
        self._prop_serial_text = ui.prop_serial_text
        self._prop_serial_text.setMaxLength(13)
        self._prop_serial_text.setText(props.serial_text or "")
        self._prop_text = ui.prop_text
        self._prop_text.setMaxLength(13)
        self._prop_text.setText(descriptor_text(self._structured, 0xFE))
        self._range_min_v = ui.range_min_v
        self._range_max_v = ui.range_max_v
        self._range_min_h = ui.range_min_h
        self._range_max_h = ui.range_max_h
        self._range_max_clock = ui.range_max_clock
        self._load_range_limits(props.range_limits)
        self._refresh_input_controls()

    def _load_range_limits(self, raw: bytes | None) -> None:
        if raw and len(raw) >= 10:
            self._range_min_v.setValue(raw[5])
            self._range_max_v.setValue(raw[6])
            self._range_min_h.setValue(raw[7])
            self._range_max_h.setValue(raw[8])
            self._range_max_clock.setValue(raw[9] * 10)
            return
        for control in (self._range_min_v, self._range_max_v, self._range_min_h, self._range_max_h, self._range_max_clock):
            control.setValue(0)

    def _refresh_input_controls(self) -> None:
        digital = self._prop_digital.isChecked()
        for control in (self._prop_bit_depth, self._prop_interface):
            control.setEnabled(digital)
        for control in (
            self._prop_analog_level,
            self._prop_separate_sync,
            self._prop_composite_sync,
            self._prop_sync_on_green,
        ):
            control.setEnabled(not digital)

    def _bind_established(self, ui: AdvancededideditordialogUi) -> None:
        self._established_list = ui.established_list
        if not self._structured:
            return
        timing_set = EstablishedTimingSet(self._structured.established_timings)
        for name, _byte, _bit in ESTABLISHED_TIMINGS:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if timing_set.is_enabled(name) else Qt.Unchecked)
            self._established_list.addItem(item)

    def _bind_standard(self, ui: AdvancededideditordialogUi) -> None:
        self._standard_list = ui.standard_list
        self._standard_width = ui.standard_width
        self._standard_height = ui.standard_height
        self._standard_height.setEnabled(False)
        self._standard_refresh = ui.standard_refresh
        self._standard_aspect = ui.standard_aspect
        for _code, ratio in ASPECT_RATIOS.items():
            self._standard_aspect.addItem(f"{ratio[0]}:{ratio[1]}", ratio)
        self._standard_width.valueChanged.connect(self._refresh_standard_height_from_aspect)
        self._standard_aspect.currentIndexChanged.connect(self._refresh_standard_height_from_aspect)
        self._standard_list.currentRowChanged.connect(self._load_standard_timing)
        if self._structured:
            self._refresh_standard()
            self._standard_list.setCurrentRow(0)
        self._refresh_standard_height_from_aspect()

    def _bind_detailed(self, ui: AdvancededideditordialogUi) -> None:
        self._detailed_list = ui.detailed_list
        self._timing_width = ui.timing_width
        self._timing_height = ui.timing_height
        self._timing_refresh = ui.timing_refresh
        self._timing_mode = ui.timing_mode
        for mode in TimingMode:
            self._timing_mode.addItem(mode.value)
        if self._structured:
            self._refresh_detailed()

    def _bind_cea(self, ui: AdvancededideditordialogUi) -> None:
        self._cea_extension_indices: list[int] = []
        self._extension_combo = ui.extension_combo
        self._cea_list = ui.cea_list
        self._cea_tag = ui.cea_tag
        self._cea_payload = ui.cea_payload
        self._cea_preset = ui.cea_preset
        for name in _CEA_PRESETS:
            self._cea_preset.addItem(name)
        self._cea_preset.currentTextChanged.connect(self._load_cea_preset)
        self._extension_combo.currentIndexChanged.connect(self._refresh_cea_list)
        if self._structured:
            self._refresh_extension_combo()

    def _bind_displayid(self, ui: AdvancededideditordialogUi) -> None:
        self._displayid_list = ui.displayid_list
        self._did_tag = ui.did_tag
        self._did_revision = ui.did_revision
        self._did_payload = ui.did_payload
        self._did_preset = ui.did_preset
        for name in _DID_PRESETS:
            self._did_preset.addItem(name)
        self._did_preset.currentTextChanged.connect(self._load_displayid_preset)
        self._refresh_displayid_list()

    def _refresh_detailed(self) -> None:
        self._detailed_list.clear()
        for index, timing in enumerate(self._structured.detailed_timings, start=1):
            refresh = timing.refresh_rate
            self._detailed_list.addItem(f"{index}: {timing.h_active}x{timing.v_active} @ {'unknown' if refresh is None else f'{refresh:.2f} Hz'}")

    def _refresh_standard(self) -> None:
        self._standard_list.clear()
        for index, timing in enumerate(self._structured.standard_timings[:8], start=1):
            if timing.is_used:
                self._standard_list.addItem(
                    f"{index}: {timing.width}x{timing.height} @ {timing.refresh_rate} Hz ({timing.aspect[0]}:{timing.aspect[1]})"
                )
            else:
                self._standard_list.addItem(f"{index}: unused")

    def _load_standard_timing(self, *_args: object) -> None:
        row = self._standard_list.currentRow()
        if not self._structured or row < 0 or row >= len(self._structured.standard_timings):
            return
        timing = self._structured.standard_timings[row]
        if not timing.is_used:
            return
        self._standard_width.setValue(timing.width)
        self._standard_refresh.setValue(timing.refresh_rate)
        aspect_index = self._standard_aspect.findData(timing.aspect)
        if aspect_index >= 0:
            self._standard_aspect.setCurrentIndex(aspect_index)
        self._refresh_standard_height_from_aspect()

    def _refresh_standard_height_from_aspect(self, *_args: object) -> None:
        aspect = self._standard_aspect.currentData() or (16, 9)
        width = self._standard_width.value()
        self._standard_height.setValue(round(width * aspect[1] / aspect[0]))

    def _standard_target_row(self) -> int:
        row = self._standard_list.currentRow()
        if 0 <= row < 8:
            return row
        for index, timing in enumerate(self._structured.standard_timings[:8]):
            if not timing.is_used:
                return index
        return 0

    def _current_standard_timing(self, index: int) -> StandardTiming:
        aspect = self._standard_aspect.currentData() or (16, 9)
        width = max(256, min(2288, (self._standard_width.value() // 8) * 8))
        if width != self._standard_width.value():
            self._standard_width.setValue(width)
        height = round(width * aspect[1] / aspect[0])
        return StandardTiming(
            index=index,
            width=width,
            height=height,
            refresh_rate=self._standard_refresh.value(),
            aspect=aspect,
            raw=b"\xff\xff",
        )

    def _replace_standard_timing(self) -> None:
        if not self._structured:
            return
        row = self._standard_target_row()
        self._structured.standard_timings[row] = self._current_standard_timing(row)
        self._refresh_standard()
        self._standard_list.setCurrentRow(row)

    def _clear_standard_timing(self) -> None:
        if not self._structured:
            return
        row = self._standard_target_row()
        self._structured.standard_timings[row] = StandardTiming.unused(row)
        self._refresh_standard()
        self._standard_list.setCurrentRow(row)

    def _apply_standard_defaults(self) -> None:
        if not self._structured:
            return
        defaults = [
            (1920, (16, 9), 60),
            (1680, (16, 10), 60),
            (1600, (16, 9), 60),
            (1440, (16, 9), 60),
            (1280, (16, 9), 60),
            (1280, (5, 4), 60),
            (1024, (4, 3), 60),
            (800, (4, 3), 60),
        ]
        self._structured.standard_timings = [
            StandardTiming(
                index=index,
                width=width,
                height=round(width * aspect[1] / aspect[0]),
                refresh_rate=refresh,
                aspect=aspect,
                raw=b"\xff\xff",
            )
            for index, (width, aspect, refresh) in enumerate(defaults)
        ]
        self._refresh_standard()
        self._standard_list.setCurrentRow(0)

    def _generated_timing(self) -> DetailedTiming:
        params = make_timing(self._timing_width.value(), self._timing_height.value(), self._timing_refresh.value(), TimingMode(self._timing_mode.currentText()))
        return DetailedTiming(params.pixel_clock_khz, params.width, params.h_blanking, params.height, params.v_blanking, params.h_front_porch, params.h_sync_width, params.v_front_porch, params.v_sync_width, 0, 0, 0, 0, params.interlaced, 0, 3, params.h_sync_positive, params.v_sync_positive, b"")

    def _add_generated_timing(self) -> None:
        if len(self._structured.detailed_timings) >= 4:
            show_message(
                self.dialog,
                key="warn_detailed_timing_limit",
                title="Detailed Timing",
                text="Base EDID can contain up to four detailed timing/descriptor slots.",
                icon=QMessageBox.Icon.Warning,
                label="Detailed timing slot limit",
            )
            return
        self._structured.detailed_timings.append(self._generated_timing())
        self._refresh_detailed()

    def _replace_generated_timing(self) -> None:
        row = self._detailed_list.currentRow()
        if 0 <= row < len(self._structured.detailed_timings):
            self._structured.detailed_timings[row] = self._generated_timing()
            self._refresh_detailed()

    def _set_preferred_timing(self) -> None:
        row = self._detailed_list.currentRow()
        if 0 <= row < len(self._structured.detailed_timings):
            self._structured.set_preferred_timing(row)
            self._refresh_detailed()

    def _delete_detailed_timing(self) -> None:
        row = self._detailed_list.currentRow()
        if 0 <= row < len(self._structured.detailed_timings):
            del self._structured.detailed_timings[row]
            self._refresh_detailed()

    def _selected_extension(self):
        index = self._extension_combo.currentIndex()
        if not self._structured or index < 0 or index >= len(self._cea_extension_indices):
            return None
        return self._structured.extensions[self._cea_extension_indices[index]]

    def _refresh_extension_combo(self) -> None:
        self._extension_combo.blockSignals(True)
        self._extension_combo.clear()
        self._cea_extension_indices = []
        for index, extension in enumerate(self._structured.extensions):
            if extension.tag != 0x02:
                continue
            self._cea_extension_indices.append(index)
            self._extension_combo.addItem(f"{extension.index}: {extension.type_name}")
        self._extension_combo.blockSignals(False)
        self._refresh_cea_list()

    def _refresh_cea_list(self) -> None:
        self._cea_list.clear()
        extension = self._selected_extension()
        if not extension:
            if self._structured:
                self._cea_list.addItem("No CEA extension selected. Use 'Add CEA Extension' to start.")
            return
        for index, block in enumerate(extension.data_blocks):
            self._cea_list.addItem(f"{index + 1}: {block.name} ({len(block.payload)} bytes)")

    def _add_cea_extension(self) -> None:
        self._structured.add_extension(ExtensionBlock(index=len(self._structured.extensions) + 1, tag=0x02, revision=3, dtd_offset=4, flags=0))
        self._refresh_extension_combo()

    def _delete_cea_extension(self) -> None:
        index = self._extension_combo.currentIndex()
        if 0 <= index < len(self._cea_extension_indices):
            self._structured.delete_extension(self._cea_extension_indices[index])
            self._refresh_extension_combo()

    def _move_extension(self, direction: int) -> None:
        index = self._extension_combo.currentIndex()
        if 0 <= index < len(self._cea_extension_indices):
            source_idx = self._cea_extension_indices[index]
            moved_idx = self._structured.move_extension(source_idx, direction)
            self._refresh_extension_combo()
            if moved_idx in self._cea_extension_indices:
                self._extension_combo.setCurrentIndex(self._cea_extension_indices.index(moved_idx))

    def _load_cea_preset(self, name: str) -> None:
        if name and name != "Custom":
            block = _CEA_PRESETS[name]()
            self._cea_tag.setValue(block.tag)
            self._cea_payload.setPlainText(_bytes_to_hex(block.payload))

    def _load_cea_block(self) -> None:
        extension = self._selected_extension()
        row = self._cea_list.currentRow()
        if extension and 0 <= row < len(extension.data_blocks):
            block = extension.data_blocks[row]
            self._cea_tag.setValue(block.tag)
            self._cea_payload.setPlainText(_bytes_to_hex(block.payload))

    def _apply_cea_block(self) -> None:
        extension = self._selected_extension()
        row = self._cea_list.currentRow()
        if extension and 0 <= row < len(extension.data_blocks):
            extension.data_blocks[row] = CEADataBlock(self._cea_tag.value(), _parse_hex(self._cea_payload.toPlainText()))
            self._refresh_cea_list()

    def _add_cea_block(self) -> None:
        extension = self._selected_extension()
        if extension:
            extension.data_blocks.append(CEADataBlock(self._cea_tag.value(), _parse_hex(self._cea_payload.toPlainText())))
            self._refresh_cea_list()

    def _delete_cea_block(self) -> None:
        extension = self._selected_extension()
        row = self._cea_list.currentRow()
        if extension and 0 <= row < len(extension.data_blocks):
            del extension.data_blocks[row]
            self._refresh_cea_list()

    def _move_cea(self, direction: int) -> None:
        extension = self._selected_extension()
        row = self._cea_list.currentRow()
        target = row + direction
        if extension and 0 <= row < len(extension.data_blocks) and 0 <= target < len(extension.data_blocks):
            extension.data_blocks[row], extension.data_blocks[target] = extension.data_blocks[target], extension.data_blocks[row]
            self._refresh_cea_list()
            self._cea_list.setCurrentRow(target)

    def _refresh_displayid_list(self) -> None:
        self._displayid_list.clear()
        if self._displayid:
            if not self._displayid.blocks:
                self._displayid_list.addItem("No DisplayID blocks yet. Choose a preset and click Add.")
            for index, block in enumerate(self._displayid.blocks):
                self._displayid_list.addItem(f"{index + 1}: {block.name} ({len(block.payload)} bytes)")
            return
        if self._structured:
            found = False
            for index, extension in enumerate(self._structured.extensions):
                if extension.tag in (0x40, 0x70):
                    found = True
                    self._displayid_list.addItem(f"{index + 1}: {extension.type_name} extension ({len(extension.raw)} bytes)")
            if not found:
                self._displayid_list.addItem("No DisplayID extensions yet. Choose a preset and click Add.")

    def _load_displayid_preset(self, name: str) -> None:
        if name and name != "Custom":
            block = _DID_PRESETS[name]()
            self._did_tag.setValue(block.tag)
            self._did_revision.setValue(block.revision)
            self._did_payload.setPlainText(_bytes_to_hex(block.payload))

    def _load_displayid_block(self) -> None:
        row = self._displayid_list.currentRow()
        if self._displayid and 0 <= row < len(self._displayid.blocks):
            block = self._displayid.blocks[row]
            self._did_tag.setValue(block.tag)
            self._did_revision.setValue(block.revision)
            self._did_payload.setPlainText(_bytes_to_hex(block.payload))
        elif self._structured:
            ext_idx = self._displayid_extension_indices()
            if 0 <= row < len(ext_idx):
                extension = self._structured.extensions[ext_idx[row]]
                self._did_tag.setValue(extension.tag)
                self._did_revision.setValue(extension.revision)
                self._did_payload.setPlainText(_bytes_to_hex(extension.raw[2:127]))

    def _apply_displayid_block(self) -> None:
        row = self._displayid_list.currentRow()
        if self._displayid and 0 <= row < len(self._displayid.blocks):
            self._displayid.blocks[row] = DisplayIDDataBlock(self._did_tag.value(), self._did_revision.value(), _parse_hex(self._did_payload.toPlainText()))
            self._refresh_displayid_list()
        elif self._structured:
            ext_idx = self._displayid_extension_indices()
            if 0 <= row < len(ext_idx):
                extension = self._structured.extensions[ext_idx[row]]
                payload = _parse_hex(self._did_payload.toPlainText())[:125]
                raw = bytearray(extension.raw[:128].ljust(128, b"\x00"))
                raw[0] = self._did_tag.value() & 0xFF
                raw[1] = self._did_revision.value() & 0xFF
                raw[2:127] = payload.ljust(125, b"\x00")
                extension.tag = raw[0]
                extension.revision = raw[1]
                extension.raw = bytes(raw)
                self._refresh_extension_combo()
                self._refresh_displayid_list()

    def _add_displayid_block(self) -> None:
        if self._displayid:
            self._displayid.blocks.append(DisplayIDDataBlock(self._did_tag.value(), self._did_revision.value(), _parse_hex(self._did_payload.toPlainText())))
            self._refresh_displayid_list()
            return
        if self._structured:
            payload = _parse_hex(self._did_payload.toPlainText())[:125]
            tag = self._did_tag.value() if self._did_tag.value() in (0x40, 0x70) else 0x70
            extension = ExtensionBlock(
                index=len(self._structured.extensions) + 1,
                tag=tag,
                revision=self._did_revision.value(),
                dtd_offset=0,
                flags=0,
                data_blocks=[],
                detailed_timings=[],
                raw=bytes([tag, self._did_revision.value() & 0xFF]) + payload.ljust(125, b"\x00") + b"\x00",
            )
            self._structured.add_extension(extension)
            self._refresh_extension_combo()
            self._refresh_displayid_list()

    def _delete_displayid_block(self) -> None:
        row = self._displayid_list.currentRow()
        if self._displayid and 0 <= row < len(self._displayid.blocks):
            del self._displayid.blocks[row]
            self._refresh_displayid_list()
        elif self._structured:
            ext_idx = self._displayid_extension_indices()
            if 0 <= row < len(ext_idx):
                self._structured.delete_extension(ext_idx[row])
                self._refresh_extension_combo()
                self._refresh_displayid_list()

    def _move_displayid(self, direction: int) -> None:
        row = self._displayid_list.currentRow()
        target = row + direction
        if self._displayid and 0 <= row < len(self._displayid.blocks) and 0 <= target < len(self._displayid.blocks):
            self._displayid.blocks[row], self._displayid.blocks[target] = self._displayid.blocks[target], self._displayid.blocks[row]
            self._refresh_displayid_list()
            self._displayid_list.setCurrentRow(target)
        elif self._structured:
            ext_idx = self._displayid_extension_indices()
            if 0 <= row < len(ext_idx) and 0 <= target < len(ext_idx):
                source_idx = ext_idx[row]
                self._structured.move_extension(source_idx, direction)
                self._refresh_extension_combo()
                self._refresh_displayid_list()
                self._displayid_list.setCurrentRow(target)

    def _displayid_extension_indices(self) -> list[int]:
        if not self._structured:
            return []
        return [index for index, extension in enumerate(self._structured.extensions) if extension.tag in (0x40, 0x70)]

    def _apply_established(self) -> None:
        if not self._structured:
            return
        timing_set = EstablishedTimingSet(bytes(3))
        for index in range(self._established_list.count()):
            item = self._established_list.item(index)
            timing_set = timing_set.set_enabled(item.text(), item.checkState() == Qt.Checked)
        self._structured.established_timings = timing_set.data

    def _apply_properties(self) -> None:
        if not self._structured:
            return
        raw = apply_common_fields(
            self._structured.raw,
            CommonEdidFields(
                manufacturer_id=self._prop_manufacturer.text().strip(),
                product_code=self._prop_product.value(),
                serial_number=int(self._prop_serial_number.text().strip() or "0"),
                manufacture_week=self._prop_week.value(),
                manufacture_year=self._prop_year.value(),
                edid_version=self._prop_version.value(),
                edid_revision=self._prop_revision.value(),
                width_cm=self._prop_width.value(),
                height_cm=self._prop_height.value(),
                gamma_byte=self._prop_gamma.value(),
            ),
        )
        if self._prop_digital.isChecked():
            raw = apply_digital_input(raw, self._prop_bit_depth.currentData(), self._prop_interface.currentData())
        else:
            raw = apply_analog_input(
                raw,
                self._prop_analog_level.currentData(),
                self._prop_separate_sync.isChecked(),
                self._prop_composite_sync.isChecked(),
                self._prop_sync_on_green.isChecked(),
            )
        raw = apply_feature_flags(
            raw,
            (
                (0x04, self._prop_srgb.isChecked()),
                (0x02, self._prop_preferred.isChecked()),
                (0x01, self._prop_continuous.isChecked()),
            ),
        )
        self._structured.raw = raw
        set_text_descriptor(self._structured, 0xFC, self._prop_name.text().strip())
        set_text_descriptor(self._structured, 0xFF, self._prop_serial_text.text().strip())
        set_text_descriptor(self._structured, 0xFE, self._prop_text.text().strip())
        set_range_descriptor(
            self._structured,
            min_v=self._range_min_v.value(),
            max_v=self._range_max_v.value(),
            min_h=self._range_min_h.value(),
            max_h=self._range_max_h.value(),
            max_clock_mhz=self._range_max_clock.value(),
        )

    def _accept(self) -> None:
        try:
            if self._structured:
                self._apply_properties()
                self._apply_established()
                self.display_data = self._structured.encode()
            elif self._displayid:
                self.display_data = self._displayid.encode()
            self.dialog.accept()
        except Exception as exc:
            log_exception("Advanced editor accept failed", exc)
            show_message(
                self.dialog,
                key="error_typed_editors_accept",
                title="Typed Editors",
                text=str(exc),
                icon=QMessageBox.Icon.Critical,
                label="Typed editors apply failure",
            )


class WorkflowEditorDialog(TypedEditorDialog):
    """Task-oriented wrapper around typed editors with review-before-apply."""

    def __init__(self, display_data: DisplayData, parent: object | None = None, *, beginner_mode: bool = True) -> None:
        self._beginner_mode = beginner_mode
        self._original_data = display_data.clone()
        super().__init__(display_data, parent)
        self._bind_mode_controls()
        self._configure_workflow_labels()
        self._apply_mode_visibility()

    def _bind_mode_controls(self) -> None:
        self._mode_toggle_button = self._ui.mode_toggle_button
        self._mode_help_label = self._ui.mode_help_label
        if self._mode_toggle_button:
            self._mode_toggle_button.clicked.connect(self._toggle_mode)

    def _configure_workflow_labels(self) -> None:
        mode = "EDID payload" if self._structured else "DisplayID payload"
        self.dialog.setWindowTitle(f"Professional EDID Editor ({mode})")
        self._set_tab_title("properties_tab", "Identity")
        self._set_tab_title("limits_tab", "Range Limits")
        self._set_tab_title("established_tab", "Compatibility")
        self._set_tab_title("standard_tab", "Standard Modes")
        self._set_tab_title("detailed_tab", "Timings")
        self._set_tab_title("cea_tab", "CTA / HDMI")
        self._set_tab_title("displayid_tab", "DisplayID")
        self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.displayid_tab), "Edit DisplayID payload blocks or DisplayID extension blocks.")

    def _set_tab_title(self, name: str, title: str) -> None:
        index = self.tabs.indexOf(getattr(self._ui, name))
        if index >= 0:
            self.tabs.setTabText(index, title)

    def _toggle_mode(self) -> None:
        self._beginner_mode = not self._beginner_mode
        self._apply_mode_visibility()

    def _set_visible(self, key: str, visible: bool) -> None:
        widget = getattr(self._ui, key, None)
        if widget is not None and hasattr(widget, "setVisible"):
            widget.setVisible(visible)

    def _apply_mode_visibility(self) -> None:
        expert = not self._beginner_mode
        if self._mode_toggle_button:
            self._mode_toggle_button.setText("Switch to Beginner" if expert else "Switch to Expert")
        if self._mode_help_label:
            self._mode_help_label.setText(
                "Expert mode: full EDID/DisplayID controls, including input coding and raw payload fields."
                if expert
                else "Beginner mode: identity, range limits, common timings, and safe HDMI/DisplayID presets."
            )
        # Hide protocol-heavy property fields in beginner mode.
        for key in (
            "prop_version",
            "prop_revision",
            "prop_digital",
            "prop_bit_depth",
            "prop_interface",
            "prop_analog_level",
            "prop_separate_sync",
            "prop_composite_sync",
            "prop_sync_on_green",
            "prop_gamma",
            "prop_text",
        ):
            self._set_visible(key, expert)
        # Beginner timing labels.
        add_button = self._ui.add_timing_button
        replace_button = self._ui.replace_timing_button
        if add_button:
            add_button.setText("Add Mode" if self._beginner_mode else "Add Timing")
        if replace_button:
            replace_button.setText("Replace Selected Mode" if self._beginner_mode else "Replace Selected")
        # Extensions: beginner mode hides raw payload editing.
        for key in ("cea_tag", "cea_payload", "extension_up_button", "extension_down_button", "up_cea_button", "down_cea_button"):
            self._set_visible(key, expert)
        # DisplayID: beginner mode hides raw protocol controls.
        for key in ("did_tag", "did_revision", "did_payload", "up_did_button", "down_did_button"):
            self._set_visible(key, expert)
        # Beginner-friendly action labels.
        rename_map = {
            "add_cea_extension_button": ("Add CEA Extension", "Add CEA Extension"),
            "apply_cea_button": ("Apply Selected Preset", "Apply"),
            "add_cea_button": ("Add Selected Preset", "Add"),
            "load_cea_button": ("Load Selected Block", "Load"),
            "apply_did_button": ("Apply Selected Preset", "Apply"),
            "add_did_button": ("Add Selected Preset", "Add"),
            "load_did_button": ("Load Selected Block", "Load"),
        }
        for key, (beginner_text, expert_text) in rename_map.items():
            widget = getattr(self._ui, key, None)
            if widget and hasattr(widget, "setText"):
                widget.setText(beginner_text if self._beginner_mode else expert_text)
        if self._beginner_mode:
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.detailed_tab), "Set the primary resolution and refresh rate here.")
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.standard_tab), "Add legacy OS fallback modes.")
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.cea_tab), "Optional HDMI/CTA extension presets.")
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.displayid_tab), "Optional DisplayID extension presets.")
        else:
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.detailed_tab), "Edit detailed timings and preferred timing order.")
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.standard_tab), "Edit the eight EDID standard timing slots.")
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.cea_tab), "Advanced CTA extension and data-block editing.")
            self.tabs.setTabToolTip(self.tabs.indexOf(self._ui.displayid_tab), "Advanced DisplayID payload and extension editing.")

    def _accept(self) -> None:
        try:
            if self._structured:
                self._apply_properties()
                self._apply_established()
                candidate = self._structured.encode()
            elif self._displayid:
                candidate = self._displayid.encode()
            else:
                return
            summary = self._review_summary(candidate)
            response = QMessageBox.question(
                self.dialog,
                "Review and apply changes",
                f"{summary}\n\nApply these changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
            self.display_data = candidate
            self.dialog.accept()
        except Exception as exc:
            log_exception("Workflow editor accept failed", exc)
            show_message(
                self.dialog,
                key="error_workflow_editor_accept",
                title="Workflow Editor",
                text=str(exc),
                icon=QMessageBox.Icon.Critical,
                label="Workflow editor apply failure",
            )

    def _review_summary(self, candidate: DisplayData) -> str:
        old_name = self._original_data.name() or "unknown"
        new_name = candidate.name() or "unknown"
        old_product = self._original_data.product_id() or "unknown"
        new_product = candidate.product_id() or "unknown"
        if candidate.data == self._original_data.data:
            return "No data changes detected."
        warning_count = len(candidate.warnings())
        return (
            f"Pending changes:\n"
            f"- Name: {old_name} -> {new_name}\n"
            f"- Product ID: {old_product} -> {new_product}\n"
            f"- Size: {self._original_data.size} bytes -> {candidate.size} bytes\n"
            f"- Validation warnings: {warning_count}"
        )


def _bytes_to_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def _parse_hex(text: str) -> bytes:
    tokens = re.findall(r"0[xX]([0-9A-Fa-f]{2})|\b([0-9A-Fa-f]{2})\b", text)
    return bytes(int(first or second, 16) for first, second in tokens)


_CEA_PRESETS = {
    "Custom": lambda: CEADataBlock(0, b""),
    "Video: 1080p60": lambda: VideoDataBlock([16]).to_block(),
    "Video: 4K60 + 4K30 + 1080p": lambda: VideoDataBlock([97, 95, 16]).to_block(),
    "Audio: LPCM stereo": lambda: AudioDataBlock([ShortAudioDescriptor(1, 2, 0x7F, 0x07)]).to_block(),
    "Audio: LPCM 8-channel": lambda: AudioDataBlock([ShortAudioDescriptor(1, 8, 0x7F, 0x07)]).to_block(),
    "Speakers: 5.1": lambda: SpeakerAllocationBlock(0x0B).to_block(),
    "Speakers: 7.1": lambda: SpeakerAllocationBlock(0x4F).to_block(),
    "HDMI VSDB: 300 MHz": lambda: HDMISupportBlock((1, 0, 0, 0), True, True, False, False, 300).to_block(),
    "HDMI Forum: FRL + DSC": lambda: HDMIForumBlock(version=1, max_frl_rate=6, supports_dsc=True).to_block(),
    "HDR10 Static Metadata": lambda: HDRStaticMetadataBlock(0x06, 0x01, 100, 80, 1).to_block(),
    "Colorimetry: BT.2020": lambda: ColorimetryBlock(0xE0, 0x00).to_block(),
    "Video Capability: selectable RGB": lambda: VideoCapabilityBlock(0x06).to_block(),
    "YCbCr 4:2:0: 4K60": lambda: YCbCr420VideoBlock([97]).to_block(),
    "Format Preference: 4K60": lambda: VideoFormatPreferenceBlock([97]).to_block(),
    "FreeSync: 48-144 Hz": lambda: FreeSyncRangeBlock(48, 144).to_block(),
}


_DID_PRESETS = {
    "Custom": lambda: DisplayIDDataBlock(0, 0, b""),
    "Display Name": lambda: DisplayIDDataBlock(0x0B, 0, b"Python Display\x00"),
    "Product Identification": lambda: DisplayIDDataBlock(0x00, 0, b"CLT\x34\x12\x01\x00\x00\x00\x01\x1AColorlight Panel\x00"),
    "Range Limits: 48-144 Hz": lambda: DisplayIDDataBlock(0x09, 0, bytes([48, 144, 30, 160, 60])),
    "Container ID": lambda: DisplayIDDataBlock(0x29, 0, bytes(16)),
}
