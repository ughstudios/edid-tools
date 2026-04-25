from __future__ import annotations

from .edid_data import DisplayData, DisplayDataError
from .edid_decode_text import decode_edid
from .logging_utils import log_exception
from .structured_edid import MonitorDescriptor, StructuredEDID

try:
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QSpinBox,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required for decoded EDID editing. Install it with: pip install PySide6") from exc


class DecodedEdidDialog(QDialog):
    """Readable EDID view with common per-field overrides."""

    def __init__(self, display_data: DisplayData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if not display_data.is_edid:
            raise DisplayDataError("Decoded EDID editing requires EDID data.")
        self.setWindowTitle("Decoded EDID")
        self.resize(760, 640)
        self._structured = StructuredEDID.parse(display_data)
        self.display_data = display_data
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.decoded_text = QPlainTextEdit()
        self.decoded_text.setReadOnly(True)
        self.decoded_text.setPlainText(decode_edid(self.display_data))
        layout.addWidget(self.decoded_text, 1)

        tabs = QTabWidget()
        tabs.addTab(self._identity_tab(), "Identity")
        tabs.addTab(self._display_tab(), "Display")
        tabs.addTab(self._color_tab(), "Color")
        tabs.addTab(self._descriptor_tab(), "Descriptors")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _identity_tab(self) -> QWidget:
        props = self._structured.properties
        tab = QWidget()
        form = QFormLayout(tab)
        self.manufacturer_edit = QLineEdit(props.manufacturer_id)
        self.product_spin = _spin(0, 0xFFFF, props.product_code)
        self.serial_number_spin = _spin(0, 0xFFFFFFFF, props.serial_number)
        self.week_spin = _spin(0, 255, props.manufacture_week)
        self.year_spin = _spin(1990, 2245, props.manufacture_year)
        self.version_spin = _spin(1, 2, props.edid_version[0])
        self.revision_spin = _spin(0, 4, props.edid_version[1])
        form.addRow("Manufacturer ID (3 letters)", self.manufacturer_edit)
        form.addRow("Product code", self.product_spin)
        form.addRow("Serial number", self.serial_number_spin)
        form.addRow("Manufacture week", self.week_spin)
        form.addRow("Manufacture year", self.year_spin)
        form.addRow("EDID version", self.version_spin)
        form.addRow("EDID revision", self.revision_spin)
        return tab

    def _display_tab(self) -> QWidget:
        props = self._structured.properties
        tab = QWidget()
        form = QFormLayout(tab)
        self.digital_check = QCheckBox("Digital input")
        self.digital_check.setChecked(props.digital_input)
        self.bit_depth_combo = QComboBox()
        for label, value in [("Undefined", 0), ("6 bpc", 1), ("8 bpc", 2), ("10 bpc", 3), ("12 bpc", 4), ("14 bpc", 5), ("16 bpc", 6)]:
            self.bit_depth_combo.addItem(label, value)
        self.bit_depth_combo.setCurrentIndex(max(0, self.bit_depth_combo.findData(_depth_code(props.bit_depth))))
        self.interface_combo = QComboBox()
        for label, value in [("Undefined", 0), ("DVI", 1), ("HDMI-a", 2), ("HDMI-b", 3), ("MDDI", 4), ("DisplayPort", 5)]:
            self.interface_combo.addItem(label, value)
        self.interface_combo.setCurrentIndex(max(0, self.interface_combo.findData(props.video_interface or 0)))
        self.analog_level_combo = QComboBox()
        for label, value in [("0.700/0.300 V", 0), ("0.714/0.286 V", 1), ("1.000/0.400 V", 2), ("0.700/0.000 V", 3)]:
            self.analog_level_combo.addItem(label, value)
        self.analog_level_combo.setCurrentIndex(max(0, self.analog_level_combo.findData(props.analog_signal_level or 0)))
        self.separate_sync_check = QCheckBox("Separate sync")
        self.separate_sync_check.setChecked(props.separate_sync)
        self.composite_sync_check = QCheckBox("Composite sync")
        self.composite_sync_check.setChecked(props.composite_sync)
        self.sync_on_green_check = QCheckBox("Sync on green")
        self.sync_on_green_check.setChecked(props.sync_on_green)
        self.width_spin = _spin(0, 255, props.width_cm)
        self.height_spin = _spin(0, 255, props.height_cm)
        self.gamma_spin = _spin(0, 255, 0 if props.gamma is None else max(0, min(255, round(props.gamma * 100 - 100))))
        self.standby_check = QCheckBox("DPMS standby")
        self.standby_check.setChecked(props.standby)
        self.suspend_check = QCheckBox("DPMS suspend")
        self.suspend_check.setChecked(props.suspend)
        self.active_off_check = QCheckBox("DPMS active off")
        self.active_off_check.setChecked(props.active_off)
        self.srgb_check = QCheckBox("sRGB")
        self.srgb_check.setChecked(props.srgb)
        self.preferred_check = QCheckBox("Preferred timing flag")
        self.preferred_check.setChecked(props.preferred_timing)
        self.continuous_check = QCheckBox("Continuous frequency")
        self.continuous_check.setChecked(props.continuous_frequency)
        form.addRow("", self.digital_check)
        form.addRow("Digital bit depth", self.bit_depth_combo)
        form.addRow("Digital interface", self.interface_combo)
        form.addRow("Analog signal level", self.analog_level_combo)
        form.addRow("", self.separate_sync_check)
        form.addRow("", self.composite_sync_check)
        form.addRow("", self.sync_on_green_check)
        form.addRow("Width (cm)", self.width_spin)
        form.addRow("Height (cm)", self.height_spin)
        form.addRow("Gamma byte (0 means unspecified)", self.gamma_spin)
        for check in (self.standby_check, self.suspend_check, self.active_off_check, self.srgb_check, self.preferred_check, self.continuous_check):
            form.addRow("", check)
        return tab

    def _color_tab(self) -> QWidget:
        base = self.display_data.data[:128]
        tab = QWidget()
        form = QFormLayout(tab)
        self.color_byte_spins: list[QSpinBox] = []
        for index in range(25, 35):
            spin = _spin(0, 255, base[index])
            self.color_byte_spins.append(spin)
            form.addRow(f"Chromaticity byte {index}", spin)
        return tab

    def _descriptor_tab(self) -> QWidget:
        props = self._structured.properties
        tab = QWidget()
        form = QFormLayout(tab)
        self.name_edit = QLineEdit(props.name or "")
        self.serial_edit = QLineEdit(props.serial_text or "")
        self.text_edit = QLineEdit(_descriptor_text(self._structured, 0xFE))
        range_raw = props.range_limits or b""
        self.range_min_v = _spin(0, 255, range_raw[5] if len(range_raw) > 5 else 0)
        self.range_max_v = _spin(0, 255, range_raw[6] if len(range_raw) > 6 else 0)
        self.range_min_h = _spin(0, 255, range_raw[7] if len(range_raw) > 7 else 0)
        self.range_max_h = _spin(0, 255, range_raw[8] if len(range_raw) > 8 else 0)
        self.range_max_clock = _spin(0, 2550, (range_raw[9] * 10) if len(range_raw) > 9 else 0)
        form.addRow("Monitor name", self.name_edit)
        form.addRow("Serial text", self.serial_edit)
        form.addRow("ASCII text", self.text_edit)
        form.addRow("Min vertical Hz", self.range_min_v)
        form.addRow("Max vertical Hz", self.range_max_v)
        form.addRow("Min horizontal kHz", self.range_min_h)
        form.addRow("Max horizontal kHz", self.range_max_h)
        form.addRow("Max pixel clock MHz", self.range_max_clock)
        return tab

    def _accept(self) -> None:
        try:
            raw = bytearray(self._structured.raw)
            raw[8:10] = _encode_manufacturer_id(self.manufacturer_edit.text().strip())
            raw[10:12] = self.product_spin.value().to_bytes(2, "little")
            raw[12:16] = self.serial_number_spin.value().to_bytes(4, "little")
            raw[16] = self.week_spin.value()
            raw[17] = self.year_spin.value() - 1990
            raw[18] = self.version_spin.value()
            raw[19] = self.revision_spin.value()
            if self.digital_check.isChecked():
                raw[20] = 0x80 | ((self.bit_depth_combo.currentData() & 0x07) << 4) | (self.interface_combo.currentData() & 0x0F)
            else:
                raw[20] = (
                    ((self.analog_level_combo.currentData() & 0x03) << 5)
                    | (0x08 if self.separate_sync_check.isChecked() else 0)
                    | (0x04 if self.composite_sync_check.isChecked() else 0)
                    | (0x02 if self.sync_on_green_check.isChecked() else 0)
                )
            raw[21] = self.width_spin.value()
            raw[22] = self.height_spin.value()
            raw[23] = 0xFF if self.gamma_spin.value() == 0 else self.gamma_spin.value()
            for offset, spin in zip(range(25, 35), self.color_byte_spins):
                raw[offset] = spin.value()
            features = raw[24]
            features = _set_bit(features, 0x80, self.standby_check.isChecked())
            features = _set_bit(features, 0x40, self.suspend_check.isChecked())
            features = _set_bit(features, 0x20, self.active_off_check.isChecked())
            features = _set_bit(features, 0x04, self.srgb_check.isChecked())
            features = _set_bit(features, 0x02, self.preferred_check.isChecked())
            features = _set_bit(features, 0x01, self.continuous_check.isChecked())
            raw[24] = features
            self._structured.raw = bytes(raw)
            self._set_text_descriptor(0xFC, self.name_edit.text().strip())
            self._set_text_descriptor(0xFF, self.serial_edit.text().strip())
            self._set_text_descriptor(0xFE, self.text_edit.text().strip())
            self._set_range_descriptor()
            self.display_data = self._structured.encode()
            self.accept()
        except Exception as exc:
            log_exception("Decoded EDID editor apply failed", exc)
            QMessageBox.critical(self, "Decoded EDID", str(exc))

    def _set_text_descriptor(self, tag: int, text: str) -> None:
        self._structured.set_descriptor_enabled(tag, bool(text))
        for descriptor in self._structured.descriptors:
            if descriptor.tag == tag:
                descriptor.text = text
                return
        if text:
            self._structured.descriptors.append(MonitorDescriptor(tag=tag, text=text, raw=b""))

    def _set_range_descriptor(self) -> None:
        if not any((self.range_min_v.value(), self.range_max_v.value(), self.range_min_h.value(), self.range_max_h.value(), self.range_max_clock.value())):
            self._structured.set_descriptor_enabled(0xFD, False)
            return
        payload = bytearray(b"\x00\x00\x00\xFD\x00" + bytes(13))
        payload[5] = self.range_min_v.value()
        payload[6] = self.range_max_v.value()
        payload[7] = self.range_min_h.value()
        payload[8] = self.range_max_h.value()
        payload[9] = min(255, self.range_max_clock.value() // 10)
        payload[10] = 0x0A
        payload[11:18] = b" " * 7
        self._structured.set_descriptor_enabled(0xFD, True)
        for descriptor in self._structured.descriptors:
            if descriptor.tag == 0xFD:
                descriptor.raw = bytes(payload)
                descriptor.text = None
                return
        self._structured.descriptors.append(MonitorDescriptor(tag=0xFD, text=None, raw=bytes(payload)))


def _set_bit(value: int, mask: int, enabled: bool) -> int:
    return (value | mask) if enabled else (value & ~mask)


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


def _descriptor_text(structured: StructuredEDID, tag: int) -> str:
    for descriptor in structured.descriptors:
        if descriptor.tag == tag:
            return descriptor.text or ""
    return ""
