from __future__ import annotations

import re

from .cea import (
    AudioDataBlock,
    ColorimetryBlock,
    HDRDynamicMetadataBlock,
    HDRStaticMetadataBlock,
    HDMISupportBlock,
    ShortAudioDescriptor,
    SpeakerAllocationBlock,
    VideoCapabilityBlock,
    VideoDataBlock,
    VideoFormatPreferenceBlock,
    YCbCr420CapabilityMapBlock,
    YCbCr420VideoBlock,
    cea_bytes_left,
)
from .displayid import DisplayIDDataBlock, DisplayIDDocument
from .edid_data import DisplayData, DisplayDataError
from .logging_utils import log_exception
from .resolutions import ESTABLISHED_TIMINGS, TimingMode, EstablishedTimingSet, make_timing
from .structured_edid import CEADataBlock, DetailedTiming, ExtensionBlock, StructuredEDID

try:
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        QStyle,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required for GUI editor mode. Install it with: pip install PySide6") from exc


class TypedEditorDialog(QDialog):
    def __init__(self, display_data: DisplayData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced EDID Editors")
        self.resize(780, 560)
        self.setMinimumSize(640, 420)
        self.display_data = display_data
        self._structured: StructuredEDID | None = None
        self._displayid: DisplayIDDocument | None = None
        if display_data.is_edid:
            self._structured = StructuredEDID.parse(display_data)
        elif display_data.is_displayid:
            self._displayid = DisplayIDDocument.parse(display_data)
        else:
            raise DisplayDataError("Typed editors require EDID or DisplayID data.")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        if self._structured:
            tabs.addTab(_scroll_tab(self._properties_tab()), "Properties")
            tabs.addTab(_scroll_tab(self._established_tab()), "Established")
            tabs.addTab(_scroll_tab(self._standard_tab()), "Standard")
            tabs.addTab(_scroll_tab(self._detailed_tab()), "Detailed")
            tabs.addTab(_scroll_tab(self._cea_tab()), "CEA / Extensions")
        if self._displayid:
            tabs.addTab(_scroll_tab(self._displayid_tab()), "DisplayID")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _properties_tab(self) -> QWidget:
        assert self._structured is not None
        props = self._structured.properties
        tab = QWidget()
        form = QFormLayout(tab)
        self._prop_manufacturer = QLineEdit(props.manufacturer_id)
        self._prop_product = _spin(0, 0xFFFF, props.product_code)
        self._prop_serial_number = QLineEdit(str(props.serial_number))
        self._prop_week = _spin(0, 255, props.manufacture_week)
        self._prop_year = _spin(1990, 2245, props.manufacture_year)
        self._prop_version = _spin(1, 2, props.edid_version[0])
        self._prop_revision = _spin(0, 4, props.edid_version[1])
        self._prop_digital = QCheckBox("Digital input")
        self._prop_digital.setChecked(props.digital_input)
        self._prop_bit_depth = QComboBox()
        for label, value in [("Undefined", 0), ("6 bpc", 1), ("8 bpc", 2), ("10 bpc", 3), ("12 bpc", 4), ("14 bpc", 5), ("16 bpc", 6)]:
            self._prop_bit_depth.addItem(label, value)
        self._prop_bit_depth.setCurrentIndex(max(0, self._prop_bit_depth.findData(_depth_code(props.bit_depth))))
        self._prop_interface = QComboBox()
        for label, value in [("Undefined", 0), ("DVI", 1), ("HDMI-a", 2), ("HDMI-b", 3), ("MDDI", 4), ("DisplayPort", 5)]:
            self._prop_interface.addItem(label, value)
        self._prop_interface.setCurrentIndex(max(0, self._prop_interface.findData(props.video_interface or 0)))
        self._prop_analog_level = QComboBox()
        for label, value in [("0.700/0.300 V", 0), ("0.714/0.286 V", 1), ("1.000/0.400 V", 2), ("0.700/0.000 V", 3)]:
            self._prop_analog_level.addItem(label, value)
        self._prop_analog_level.setCurrentIndex(max(0, self._prop_analog_level.findData(props.analog_signal_level or 0)))
        self._prop_separate_sync = QCheckBox("Separate sync")
        self._prop_separate_sync.setChecked(props.separate_sync)
        self._prop_composite_sync = QCheckBox("Composite sync")
        self._prop_composite_sync.setChecked(props.composite_sync)
        self._prop_sync_green = QCheckBox("Sync on green")
        self._prop_sync_green.setChecked(props.sync_on_green)
        self._prop_width = _spin(0, 255, props.width_cm)
        self._prop_height = _spin(0, 255, props.height_cm)
        self._prop_gamma = _spin(0, 255, 0 if props.gamma is None else round(props.gamma * 100 - 100))
        self._prop_standby = QCheckBox("DPMS standby")
        self._prop_standby.setChecked(props.standby)
        self._prop_suspend = QCheckBox("DPMS suspend")
        self._prop_suspend.setChecked(props.suspend)
        self._prop_active_off = QCheckBox("DPMS active off")
        self._prop_active_off.setChecked(props.active_off)
        self._prop_srgb = QCheckBox("sRGB")
        self._prop_srgb.setChecked(props.srgb)
        self._prop_preferred = QCheckBox("First detailed timing is preferred")
        self._prop_preferred.setChecked(props.preferred_timing)
        self._prop_continuous = QCheckBox("Continuous frequency")
        self._prop_continuous.setChecked(props.continuous_frequency)
        self._prop_name = QLineEdit(props.name or "")
        self._prop_serial_text = QLineEdit(props.serial_text or "")
        self._prop_text = QLineEdit(_descriptor_text(self._structured, 0xFE))
        self._prop_color_bytes: list[QSpinBox] = []
        base = self._structured.raw[:128]

        form.addRow("Manufacturer ID", self._prop_manufacturer)
        form.addRow("Product Code", self._prop_product)
        form.addRow("Serial Number", self._prop_serial_number)
        form.addRow("Manufacture Week", self._prop_week)
        form.addRow("Manufacture Year", self._prop_year)
        form.addRow("EDID Version", self._prop_version)
        form.addRow("EDID Revision", self._prop_revision)
        form.addRow("", self._prop_digital)
        form.addRow("Digital Bit Depth", self._prop_bit_depth)
        form.addRow("Digital Interface", self._prop_interface)
        form.addRow("Analog Signal Level", self._prop_analog_level)
        for check in (self._prop_separate_sync, self._prop_composite_sync, self._prop_sync_green):
            form.addRow("", check)
        form.addRow("Width (cm)", self._prop_width)
        form.addRow("Height (cm)", self._prop_height)
        form.addRow("Gamma byte (0 = unspecified)", self._prop_gamma)
        for check in (self._prop_standby, self._prop_suspend, self._prop_active_off, self._prop_srgb, self._prop_preferred, self._prop_continuous):
            form.addRow("", check)
        form.addRow("Monitor Name", self._prop_name)
        form.addRow("Serial Text", self._prop_serial_text)
        form.addRow("ASCII Text", self._prop_text)
        for index in range(25, 35):
            spin = _spin(0, 255, base[index])
            self._prop_color_bytes.append(spin)
            form.addRow(f"Chromaticity byte {index}", spin)
        self._descriptor_checks: dict[int, QCheckBox] = {}
        for tag, label in ((0xFC, "Include monitor name descriptor"), (0xFF, "Include serial descriptor"), (0xFE, "Include text descriptor"), (0xFD, "Include range limits descriptor")):
            check = QCheckBox(label)
            check.setChecked(any(descriptor.tag == tag for descriptor in self._structured.descriptors))
            self._descriptor_checks[tag] = check
            form.addRow("", check)
        return tab

    def _established_tab(self) -> QWidget:
        assert self._structured is not None
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._established_checks: dict[str, QCheckBox] = {}
        timing_set = EstablishedTimingSet(self._structured.established_timings)
        for name, _byte, _bit in ESTABLISHED_TIMINGS:
            check = QCheckBox(name)
            check.setChecked(timing_set.is_enabled(name))
            self._established_checks[name] = check
            layout.addWidget(check)
        layout.addStretch(1)
        return tab

    def _standard_tab(self) -> QWidget:
        assert self._structured is not None
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._standard_list = QListWidget()
        for timing in self._structured.standard_timings:
            text = "Unused" if not timing.is_used else f"{timing.width}x{timing.height} @ {timing.refresh_rate} Hz"
            self._standard_list.addItem(f"{timing.index + 1}: {text}")
        layout.addWidget(self._standard_list)
        layout.addWidget(QLabel("Standard timing editing is preserved through the model; use raw block editor for uncommon encodings."))
        return tab

    def _detailed_tab(self) -> QWidget:
        assert self._structured is not None
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._detailed_list = QListWidget()
        for index, timing in enumerate(self._structured.detailed_timings, start=1):
            refresh = timing.refresh_rate
            refresh_text = "unknown" if refresh is None else f"{refresh:.2f} Hz"
            self._detailed_list.addItem(
                f"{index}: {timing.h_active}x{timing.v_active} @ {refresh_text}, "
                f"{timing.pixel_clock_khz / 1000:.3f} MHz"
            )
        if self._detailed_list.count() == 0:
            self._detailed_list.addItem("No base detailed timings")
        layout.addWidget(self._detailed_list)
        form = QFormLayout()
        self._timing_width = QSpinBox()
        self._timing_width.setRange(1, 8192)
        self._timing_width.setValue(1920)
        self._timing_height = QSpinBox()
        self._timing_height.setRange(1, 8192)
        self._timing_height.setValue(1080)
        self._timing_refresh = QSpinBox()
        self._timing_refresh.setRange(1, 1000)
        self._timing_refresh.setValue(60)
        self._timing_mode = QComboBox()
        for mode in TimingMode:
            self._timing_mode.addItem(mode.value)
        form.addRow("Width", self._timing_width)
        form.addRow("Height", self._timing_height)
        form.addRow("Refresh", self._timing_refresh)
        form.addRow("Mode", self._timing_mode)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        for text, slot in [
            ("Add Timing", self._add_generated_timing),
            ("Replace Selected", self._replace_generated_timing),
            ("Set Preferred", self._set_preferred_timing),
            ("Delete", self._delete_detailed_timing),
        ]:
            button = _button(self, text, _button_icon(text), _button_tip(text, "detailed timing"))
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        return tab

    def _cea_tab(self) -> QWidget:
        assert self._structured is not None
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._extension_combo = QComboBox()
        for extension in self._structured.extensions:
            self._extension_combo.addItem(f"{extension.index}: {extension.type_name}")
        self._extension_combo.currentIndexChanged.connect(self._refresh_cea_list)
        layout.addWidget(self._extension_combo)
        extension_buttons = QHBoxLayout()
        for text, slot in [
            ("Add CEA Extension", self._add_cea_extension),
            ("Delete Extension", self._delete_cea_extension),
            ("Extension Up", lambda: self._move_extension(-1)),
            ("Extension Down", lambda: self._move_extension(1)),
        ]:
            button = _button(self, text, _button_icon(text), _button_tip(text, "extension"))
            button.clicked.connect(slot)
            extension_buttons.addWidget(button)
        layout.addLayout(extension_buttons)

        self._cea_list = QListWidget()
        layout.addWidget(self._cea_list, 1)

        edit_group = QGroupBox("Selected CEA Data Block")
        form = QFormLayout(edit_group)
        self._cea_tag = QSpinBox()
        self._cea_tag.setRange(0, 7)
        self._cea_payload = QTextEdit()
        self._cea_payload.setMaximumHeight(90)
        self._cea_preset = QComboBox()
        for name in _CEA_PRESETS:
            self._cea_preset.addItem(name)
        self._cea_preset.currentTextChanged.connect(self._load_cea_preset)
        form.addRow("Tag", self._cea_tag)
        form.addRow("Payload Hex", self._cea_payload)
        form.addRow("Preset", self._cea_preset)
        layout.addWidget(edit_group)

        buttons = QHBoxLayout()
        for text, slot in [
            ("Load", self._load_cea_block),
            ("Apply", self._apply_cea_block),
            ("Add", self._add_cea_block),
            ("Delete", self._delete_cea_block),
            ("Up", lambda: self._move_cea(-1)),
            ("Down", lambda: self._move_cea(1)),
        ]:
            button = _button(self, text, _button_icon(text), _button_tip(text, "CEA data block"))
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._refresh_cea_list()
        return tab

    def _displayid_tab(self) -> QWidget:
        assert self._displayid is not None
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._displayid_list = QListWidget()
        layout.addWidget(self._displayid_list, 1)
        edit_group = QGroupBox("Selected DisplayID Data Block")
        form = QFormLayout(edit_group)
        self._did_tag = QSpinBox()
        self._did_tag.setRange(0, 255)
        self._did_revision = QSpinBox()
        self._did_revision.setRange(0, 255)
        self._did_payload = QTextEdit()
        self._did_payload.setMaximumHeight(100)
        self._did_preset = QComboBox()
        for name in _DID_PRESETS:
            self._did_preset.addItem(name)
        self._did_preset.currentTextChanged.connect(self._load_displayid_preset)
        form.addRow("Tag", self._did_tag)
        form.addRow("Revision", self._did_revision)
        form.addRow("Payload Hex", self._did_payload)
        form.addRow("Preset", self._did_preset)
        layout.addWidget(edit_group)
        buttons = QHBoxLayout()
        for text, slot in [
            ("Load", self._load_displayid_block),
            ("Apply", self._apply_displayid_block),
            ("Add", self._add_displayid_block),
            ("Delete", self._delete_displayid_block),
            ("Up", lambda: self._move_displayid(-1)),
            ("Down", lambda: self._move_displayid(1)),
        ]:
            button = _button(self, text, _button_icon(text), _button_tip(text, "DisplayID data block"))
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._refresh_displayid_list()
        return tab

    def _selected_extension(self):
        assert self._structured is not None
        index = self._extension_combo.currentIndex()
        if index < 0 or index >= len(self._structured.extensions):
            return None
        return self._structured.extensions[index]

    def _refresh_detailed_list(self) -> None:
        self._detailed_list.clear()
        assert self._structured is not None
        for index, timing in enumerate(self._structured.detailed_timings, start=1):
            refresh = timing.refresh_rate
            refresh_text = "unknown" if refresh is None else f"{refresh:.2f} Hz"
            prefix = "preferred, " if index == 1 else ""
            self._detailed_list.addItem(f"{index}: {prefix}{timing.h_active}x{timing.v_active} @ {refresh_text}")
        if self._detailed_list.count() == 0:
            self._detailed_list.addItem("No base detailed timings")

    def _generated_timing(self) -> DetailedTiming:
        params = make_timing(
            self._timing_width.value(),
            self._timing_height.value(),
            self._timing_refresh.value(),
            TimingMode(self._timing_mode.currentText()),
        )
        return DetailedTiming(
            pixel_clock_khz=params.pixel_clock_khz,
            h_active=params.width,
            h_blanking=params.h_blanking,
            v_active=params.height,
            v_blanking=params.v_blanking,
            h_sync_offset=params.h_front_porch,
            h_sync_width=params.h_sync_width,
            v_sync_offset=params.v_front_porch,
            v_sync_width=params.v_sync_width,
            h_size_mm=0,
            v_size_mm=0,
            h_border=0,
            v_border=0,
            interlaced=params.interlaced,
            stereo=0,
            sync_type=3,
            positive_hsync=params.h_sync_positive,
            positive_vsync=params.v_sync_positive,
            raw=b"",
        )

    def _add_generated_timing(self) -> None:
        assert self._structured is not None
        if len(self._structured.detailed_timings) >= 4:
            QMessageBox.warning(self, "Detailed Timing", "Base EDID can contain up to four detailed timing/descriptor slots.")
            return
        self._structured.detailed_timings.append(self._generated_timing())
        self._refresh_detailed_list()

    def _replace_generated_timing(self) -> None:
        assert self._structured is not None
        index = self._detailed_list.currentRow()
        if 0 <= index < len(self._structured.detailed_timings):
            self._structured.detailed_timings[index] = self._generated_timing()
            self._refresh_detailed_list()

    def _set_preferred_timing(self) -> None:
        assert self._structured is not None
        index = self._detailed_list.currentRow()
        if 0 <= index < len(self._structured.detailed_timings):
            self._structured.set_preferred_timing(index)
            self._refresh_detailed_list()

    def _delete_detailed_timing(self) -> None:
        assert self._structured is not None
        index = self._detailed_list.currentRow()
        if 0 <= index < len(self._structured.detailed_timings):
            del self._structured.detailed_timings[index]
            self._refresh_detailed_list()

    def _refresh_cea_list(self) -> None:
        self._cea_list.clear()
        extension = self._selected_extension()
        if not extension:
            return
        for index, block in enumerate(extension.data_blocks):
            self._cea_list.addItem(f"{index + 1}: {block.name} ({len(block.payload)} bytes)")
        self._cea_list.addItem(f"Bytes left: {cea_bytes_left(extension.data_blocks, dtd_bytes=len(extension.detailed_timings) * 18)}")

    def _refresh_extension_combo(self) -> None:
        assert self._structured is not None
        current = max(0, self._extension_combo.currentIndex())
        self._extension_combo.blockSignals(True)
        self._extension_combo.clear()
        for extension in self._structured.extensions:
            self._extension_combo.addItem(f"{extension.index}: {extension.type_name}")
        self._extension_combo.setCurrentIndex(min(current, len(self._structured.extensions) - 1))
        self._extension_combo.blockSignals(False)
        self._refresh_cea_list()

    def _add_cea_extension(self) -> None:
        assert self._structured is not None
        try:
            self._structured.add_extension(ExtensionBlock(index=len(self._structured.extensions) + 1, tag=0x02, revision=3, dtd_offset=4, flags=0))
            self._refresh_extension_combo()
        except Exception as exc:
            log_exception("Advanced editor extension add failed", exc)
            QMessageBox.critical(self, "Extension", str(exc))

    def _delete_cea_extension(self) -> None:
        assert self._structured is not None
        index = self._extension_combo.currentIndex()
        if 0 <= index < len(self._structured.extensions):
            self._structured.delete_extension(index)
            self._refresh_extension_combo()

    def _move_extension(self, direction: int) -> None:
        assert self._structured is not None
        index = self._extension_combo.currentIndex()
        if 0 <= index < len(self._structured.extensions):
            target = self._structured.move_extension(index, direction)
            self._refresh_extension_combo()
            self._extension_combo.setCurrentIndex(target)

    def _load_cea_preset(self, name: str) -> None:
        if not name or name == "Custom":
            return
        block = _CEA_PRESETS[name]()
        self._cea_tag.setValue(block.tag)
        self._cea_payload.setPlainText(_bytes_to_hex(block.payload))

    def _load_cea_block(self) -> None:
        extension = self._selected_extension()
        index = self._cea_list.currentRow()
        if not extension or index < 0 or index >= len(extension.data_blocks):
            return
        block = extension.data_blocks[index]
        self._cea_tag.setValue(block.tag)
        self._cea_payload.setPlainText(_bytes_to_hex(block.payload))

    def _apply_cea_block(self) -> None:
        extension = self._selected_extension()
        index = self._cea_list.currentRow()
        if not extension or index < 0 or index >= len(extension.data_blocks):
            return
        try:
            extension.data_blocks[index] = CEADataBlock(self._cea_tag.value(), _parse_hex(self._cea_payload.toPlainText()))
            self._refresh_cea_list()
        except Exception as exc:
            log_exception("Advanced editor CEA block apply failed", exc)
            QMessageBox.critical(self, "CEA Data Block", str(exc))

    def _add_cea_block(self) -> None:
        extension = self._selected_extension()
        if not extension:
            return
        try:
            extension.data_blocks.append(CEADataBlock(self._cea_tag.value(), _parse_hex(self._cea_payload.toPlainText())))
            self._refresh_cea_list()
        except Exception as exc:
            log_exception("Advanced editor CEA block add failed", exc)
            QMessageBox.critical(self, "CEA Data Block", str(exc))

    def _delete_cea_block(self) -> None:
        extension = self._selected_extension()
        index = self._cea_list.currentRow()
        if extension and 0 <= index < len(extension.data_blocks):
            del extension.data_blocks[index]
            self._refresh_cea_list()

    def _move_cea(self, direction: int) -> None:
        extension = self._selected_extension()
        index = self._cea_list.currentRow()
        if not extension:
            return
        target = index + direction
        if 0 <= index < len(extension.data_blocks) and 0 <= target < len(extension.data_blocks):
            extension.data_blocks[index], extension.data_blocks[target] = extension.data_blocks[target], extension.data_blocks[index]
            self._refresh_cea_list()
            self._cea_list.setCurrentRow(target)

    def _refresh_displayid_list(self) -> None:
        assert self._displayid is not None
        self._displayid_list.clear()
        for index, block in enumerate(self._displayid.blocks):
            self._displayid_list.addItem(f"{index + 1}: {block.name} ({len(block.payload)} bytes)")

    def _load_displayid_preset(self, name: str) -> None:
        if not name or name == "Custom":
            return
        block = _DID_PRESETS[name]()
        self._did_tag.setValue(block.tag)
        self._did_revision.setValue(block.revision)
        self._did_payload.setPlainText(_bytes_to_hex(block.payload))

    def _load_displayid_block(self) -> None:
        assert self._displayid is not None
        index = self._displayid_list.currentRow()
        if 0 <= index < len(self._displayid.blocks):
            block = self._displayid.blocks[index]
            self._did_tag.setValue(block.tag)
            self._did_revision.setValue(block.revision)
            self._did_payload.setPlainText(_bytes_to_hex(block.payload))

    def _apply_displayid_block(self) -> None:
        assert self._displayid is not None
        index = self._displayid_list.currentRow()
        if 0 <= index < len(self._displayid.blocks):
            try:
                self._displayid.blocks[index] = DisplayIDDataBlock(
                    self._did_tag.value(),
                    self._did_revision.value(),
                    _parse_hex(self._did_payload.toPlainText()),
                )
                self._refresh_displayid_list()
            except Exception as exc:
                log_exception("Advanced editor DisplayID block apply failed", exc)
                QMessageBox.critical(self, "DisplayID Data Block", str(exc))

    def _add_displayid_block(self) -> None:
        assert self._displayid is not None
        try:
            self._displayid.blocks.append(
                DisplayIDDataBlock(self._did_tag.value(), self._did_revision.value(), _parse_hex(self._did_payload.toPlainText()))
            )
            self._refresh_displayid_list()
        except Exception as exc:
            log_exception("Advanced editor DisplayID block add failed", exc)
            QMessageBox.critical(self, "DisplayID Data Block", str(exc))

    def _delete_displayid_block(self) -> None:
        assert self._displayid is not None
        index = self._displayid_list.currentRow()
        if 0 <= index < len(self._displayid.blocks):
            del self._displayid.blocks[index]
            self._refresh_displayid_list()

    def _move_displayid(self, direction: int) -> None:
        assert self._displayid is not None
        index = self._displayid_list.currentRow()
        target = index + direction
        if 0 <= index < len(self._displayid.blocks) and 0 <= target < len(self._displayid.blocks):
            self._displayid.blocks[index], self._displayid.blocks[target] = self._displayid.blocks[target], self._displayid.blocks[index]
            self._refresh_displayid_list()
            self._displayid_list.setCurrentRow(target)

    def _apply_established(self) -> None:
        if not self._structured:
            return
        timing_set = EstablishedTimingSet(self._structured.established_timings)
        for name, check in self._established_checks.items():
            timing_set = timing_set.set_enabled(name, check.isChecked())
        self._structured.established_timings = timing_set.data
        raw = bytearray(self._structured.raw)
        raw[35:38] = timing_set.data
        raw[127] = (-sum(raw[:127])) & 0xFF
        self._structured.raw = bytes(raw)

    def _apply_properties(self) -> None:
        if not self._structured:
            return
        raw = bytearray(self._structured.raw)
        raw[8:10] = _encode_manufacturer_id(self._prop_manufacturer.text().strip())
        raw[10:12] = self._prop_product.value().to_bytes(2, "little")
        raw[12:16] = (int(self._prop_serial_number.text().strip() or "0") & 0xFFFFFFFF).to_bytes(4, "little")
        raw[16] = self._prop_week.value()
        raw[17] = self._prop_year.value() - 1990
        raw[18] = self._prop_version.value()
        raw[19] = self._prop_revision.value()
        if self._prop_digital.isChecked():
            raw[20] = 0x80 | ((self._prop_bit_depth.currentData() & 0x07) << 4) | (self._prop_interface.currentData() & 0x0F)
        else:
            raw[20] = (
                ((self._prop_analog_level.currentData() & 0x03) << 5)
                | (0x08 if self._prop_separate_sync.isChecked() else 0)
                | (0x04 if self._prop_composite_sync.isChecked() else 0)
                | (0x02 if self._prop_sync_green.isChecked() else 0)
            )
        raw[21] = self._prop_width.value()
        raw[22] = self._prop_height.value()
        raw[23] = 0xFF if self._prop_gamma.value() == 0 else self._prop_gamma.value()
        features = raw[24]
        for mask, check in (
            (0x80, self._prop_standby),
            (0x40, self._prop_suspend),
            (0x20, self._prop_active_off),
            (0x04, self._prop_srgb),
            (0x02, self._prop_preferred),
            (0x01, self._prop_continuous),
        ):
            features = _set_bit(features, mask, check.isChecked())
        raw[24] = features
        for offset, spin in zip(range(25, 35), self._prop_color_bytes):
            raw[offset] = spin.value()
        self._structured.raw = bytes(raw)
        self._set_text_descriptor(0xFC, self._prop_name.text().strip(), self._descriptor_checks[0xFC].isChecked())
        self._set_text_descriptor(0xFF, self._prop_serial_text.text().strip(), self._descriptor_checks[0xFF].isChecked())
        self._set_text_descriptor(0xFE, self._prop_text.text().strip(), self._descriptor_checks[0xFE].isChecked())

    def _set_text_descriptor(self, tag: int, text: str, enabled: bool) -> None:
        self._structured.set_descriptor_enabled(tag, enabled)
        if not enabled:
            return
        for descriptor in self._structured.descriptors:
            if descriptor.tag == tag:
                descriptor.text = text
                return

    def _apply_descriptor_toggles(self) -> None:
        if not self._structured:
            return
        for tag, check in getattr(self, "_descriptor_checks", {}).items():
            self._structured.set_descriptor_enabled(tag, check.isChecked())

    def _accept(self) -> None:
        try:
            if self._structured:
                self._apply_properties()
                self._apply_established()
                self.display_data = self._structured.encode()
            elif self._displayid:
                self.display_data = self._displayid.encode()
            self.accept()
        except Exception as exc:
            log_exception("Advanced editor accept failed", exc)
            QMessageBox.critical(self, "Typed Editors", str(exc))


def _bytes_to_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def _scroll_tab(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(widget)
    return scroll


def _button(parent: QWidget, text: str, icon: QStyle.StandardPixmap, tooltip: str | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setIcon(parent.style().standardIcon(icon))
    button.setIconSize(QSize(18, 18))
    if tooltip:
        button.setToolTip(tooltip)
    return button


def _button_icon(text: str) -> QStyle.StandardPixmap:
    if text.startswith("Add"):
        return QStyle.SP_FileDialogNewFolder
    if text.startswith("Replace") or text.startswith("Apply") or text == "Set Preferred":
        return QStyle.SP_DialogApplyButton
    if text == "Load":
        return QStyle.SP_DialogOpenButton
    if text == "Delete":
        return QStyle.SP_TrashIcon
    if text in {"Up", "Extension Up"}:
        return QStyle.SP_ArrowUp
    if text in {"Down", "Extension Down"}:
        return QStyle.SP_ArrowDown
    return QStyle.SP_FileIcon


def _button_tip(text: str, target: str) -> str:
    if text.startswith("Add"):
        return f"Add a new {target}."
    if text.startswith("Replace"):
        return f"Replace the selected {target}."
    if text == "Set Preferred":
        return "Make the selected detailed timing the preferred/native timing."
    if text == "Load":
        return f"Load the selected {target} into the editor fields."
    if text == "Apply":
        return f"Apply the editor fields to the selected {target}."
    if text == "Delete":
        return f"Delete the selected {target}."
    if "Up" in text:
        return f"Move the selected {target} up."
    if "Down" in text:
        return f"Move the selected {target} down."
    return ""


def _parse_hex(text: str) -> bytes:
    tokens = re.findall(r"0[xX]([0-9A-Fa-f]{2})|\b([0-9A-Fa-f]{2})\b", text)
    return bytes(int(first or second, 16) for first, second in tokens)


def _spin(minimum: int, maximum: int, value: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(max(minimum, min(maximum, value)))
    return spin


def _depth_code(bit_depth: int | None) -> int:
    return {6: 1, 8: 2, 10: 3, 12: 4, 14: 5, 16: 6}.get(bit_depth or 0, 0)


def _encode_manufacturer_id(value: str) -> bytes:
    text = (value.upper() + "   ")[:3]
    values = [max(1, min(26, ord(char) - 64)) for char in text]
    packed = (values[0] << 10) | (values[1] << 5) | values[2]
    return packed.to_bytes(2, "big")


def _set_bit(value: int, mask: int, enabled: bool) -> int:
    return (value | mask) if enabled else (value & ~mask)


def _descriptor_text(structured: StructuredEDID, tag: int) -> str:
    for descriptor in structured.descriptors:
        if descriptor.tag == tag:
            return descriptor.text or ""
    return ""


_CEA_PRESETS = {
    "Custom": lambda: CEADataBlock(0, b""),
    "Video: 1080p60": lambda: VideoDataBlock([16]).to_block(),
    "Audio: LPCM stereo": lambda: AudioDataBlock([ShortAudioDescriptor(1, 2, 0x7F, 0x07)]).to_block(),
    "Speaker: 5.1": lambda: SpeakerAllocationBlock(0x0B).to_block(),
    "HDMI VSDB": lambda: HDMISupportBlock((1, 0, 0, 0), True, True, False, False, 300).to_block(),
    "HDR Static": lambda: HDRStaticMetadataBlock(0x05, 0x01, 100, 80, 10).to_block(),
    "HDR Dynamic": lambda: HDRDynamicMetadataBlock(b"\x01\x00").to_block(),
    "Colorimetry": lambda: ColorimetryBlock(0xE0, 0x00).to_block(),
    "Video Capability": lambda: VideoCapabilityBlock(0x78).to_block(),
    "YCbCr 4:2:0 Video": lambda: YCbCr420VideoBlock([97]).to_block(),
    "YCbCr 4:2:0 Map": lambda: YCbCr420CapabilityMapBlock(b"\x01").to_block(),
    "Video Format Preference": lambda: VideoFormatPreferenceBlock([16]).to_block(),
}


_DID_PRESETS = {
    "Custom": lambda: DisplayIDDataBlock(0, 0, b""),
    "Product Identification": lambda: DisplayIDDataBlock(0x20, 0, b"PYD\x34\x12\x00\x00\x00\x00\x01\x1A Python Display\x00"),
    "Display Parameters": lambda: DisplayIDDataBlock(0x21, 0, b"\x00\x00\x00\x00\x00"),
    "Range Limits": lambda: DisplayIDDataBlock(0x25, 0, b"\x30\x90\x1E\xA0\x3C"),
    "Display Name": lambda: DisplayIDDataBlock(0x0B, 0, b"Python Display\x00"),
    "Container ID": lambda: DisplayIDDataBlock(0x29, 0, bytes(16)),
}
