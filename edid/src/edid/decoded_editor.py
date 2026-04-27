from __future__ import annotations

from edid.edid_edit_service import (
    CommonEdidFields,
    apply_analog_input,
    apply_color_bytes,
    apply_common_fields,
    apply_digital_input,
    apply_feature_flags,
    depth_code,
    descriptor_text,
    set_range_descriptor,
    set_text_descriptor,
)
from edid.edid_data import DisplayData, DisplayDataError
from edid.edid_decode_text import decode_edid
from edid.dialog_preferences import show_message
from edid.logging_utils import log_exception
from edid.structured_edid import StructuredEDID
from edid.ui_factory import load_ui, xml_root_dir
from edid.ui.decodedediddialog import (
    analog_level_combo,
    bit_depth_combo,
    buttons,
    decoded_text,
    digital_check,
    gamma_spin,
    height_spin,
    interface_combo,
    manufacturer_edit,
    name_edit,
    product_spin,
    range_max_clock,
    revision_spin,
    serial_edit,
    serial_number_edit,
    text_edit,
    version_spin,
    week_spin,
    width_spin,
    year_spin,
)

try:
    from PySide6.QtWidgets import QMessageBox
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required for decoded EDID editing. Install it with: pip install PySide6") from exc


class DecodedEdidDialog:
    """Readable EDID view with common per-field overrides."""

    def __init__(self, display_data: DisplayData, parent: object | None = None) -> None:
        if not display_data.is_edid:
            raise DisplayDataError("Decoded EDID editing requires EDID data.")
        ui = load_ui(xml_root_dir() / "decoded_edid_dialog.xml")
        self.dialog = ui.root
        self.dialog.resize(760, 640)
        self._structured = StructuredEDID.parse(display_data)
        self.display_data = display_data
        self._bind(ui)

    def exec(self) -> int:
        return self.dialog.exec()

    def _bind(self, ui: object) -> None:
        props = self._structured.properties
        ui[decoded_text].setPlainText(decode_edid(self.display_data))
        self.manufacturer_edit = ui[manufacturer_edit]
        self.manufacturer_edit.setMaxLength(3)
        self.manufacturer_edit.setText(props.manufacturer_id)
        self.product_spin = ui[product_spin]
        self.product_spin.setValue(props.product_code)
        self.serial_number_edit = ui[serial_number_edit]
        self.serial_number_edit.setText(str(props.serial_number))
        self.week_spin = ui[week_spin]
        self.week_spin.setValue(props.manufacture_week)
        self.year_spin = ui[year_spin]
        self.year_spin.setValue(props.manufacture_year)
        self.version_spin = ui[version_spin]
        self.version_spin.setValue(props.edid_version[0])
        self.revision_spin = ui[revision_spin]
        self.revision_spin.setValue(props.edid_version[1])
        self.digital_check = ui[digital_check]
        self.digital_check.setChecked(props.digital_input)
        self.bit_depth_combo = ui[bit_depth_combo]
        for label, value in [("Undefined", 0), ("6 bpc", 1), ("8 bpc", 2), ("10 bpc", 3), ("12 bpc", 4), ("14 bpc", 5), ("16 bpc", 6)]:
            self.bit_depth_combo.addItem(label, value)
        self.bit_depth_combo.setCurrentIndex(max(0, self.bit_depth_combo.findData(depth_code(props.bit_depth))))
        self.interface_combo = ui[interface_combo]
        for label, value in [("Undefined", 0), ("DVI", 1), ("HDMI-a", 2), ("HDMI-b", 3), ("MDDI", 4), ("DisplayPort", 5)]:
            self.interface_combo.addItem(label, value)
        self.interface_combo.setCurrentIndex(max(0, self.interface_combo.findData(props.video_interface or 0)))
        self.analog_level_combo = ui[analog_level_combo]
        for label, value in [("0.700/0.300 V", 0), ("0.714/0.286 V", 1), ("1.000/0.400 V", 2), ("0.700/0.000 V", 3)]:
            self.analog_level_combo.addItem(label, value)
        self.analog_level_combo.setCurrentIndex(max(0, self.analog_level_combo.findData(props.analog_signal_level or 0)))
        for name, value in (
            ("separate_sync_check", props.separate_sync),
            ("composite_sync_check", props.composite_sync),
            ("sync_on_green_check", props.sync_on_green),
            ("standby_check", props.standby),
            ("suspend_check", props.suspend),
            ("active_off_check", props.active_off),
            ("srgb_check", props.srgb),
            ("preferred_check", props.preferred_timing),
            ("continuous_check", props.continuous_frequency),
        ):
            setattr(self, name, ui[name])
            ui[name].setChecked(value)
        self.width_spin = ui[width_spin]
        self.width_spin.setValue(props.width_cm)
        self.height_spin = ui[height_spin]
        self.height_spin.setValue(props.height_cm)
        self.gamma_spin = ui[gamma_spin]
        self.gamma_spin.setValue(0 if props.gamma is None else max(0, min(255, round(props.gamma * 100 - 100))))
        base = self.display_data.data[:128]
        self.color_byte_spins = [ui[f"color_{index}"] for index in range(25, 35)]
        for offset, spin in zip(range(25, 35), self.color_byte_spins):
            spin.setValue(base[offset])
        self.name_edit = ui[name_edit]
        self.name_edit.setText(props.name or "")
        self.serial_edit = ui[serial_edit]
        self.serial_edit.setText(props.serial_text or "")
        self.text_edit = ui[text_edit]
        self.text_edit.setText(descriptor_text(self._structured, 0xFE))
        range_raw = props.range_limits or b""
        for attr, offset in (
            ("range_min_v", 5),
            ("range_max_v", 6),
            ("range_min_h", 7),
            ("range_max_h", 8),
        ):
            setattr(self, attr, ui[attr])
            ui[attr].setValue(range_raw[offset] if len(range_raw) > offset else 0)
        self.range_max_clock = ui[range_max_clock]
        self.range_max_clock.setValue((range_raw[9] * 10) if len(range_raw) > 9 else 0)
        button_box = ui[buttons]
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.dialog.reject)

    def _accept(self) -> None:
        try:
            raw = apply_common_fields(
                self._structured.raw,
                CommonEdidFields(
                    manufacturer_id=self.manufacturer_edit.text().strip(),
                    product_code=self.product_spin.value(),
                    serial_number=int(self.serial_number_edit.text().strip() or "0"),
                    manufacture_week=self.week_spin.value(),
                    manufacture_year=self.year_spin.value(),
                    edid_version=self.version_spin.value(),
                    edid_revision=self.revision_spin.value(),
                    width_cm=self.width_spin.value(),
                    height_cm=self.height_spin.value(),
                    gamma_byte=self.gamma_spin.value(),
                ),
            )
            if self.digital_check.isChecked():
                raw = apply_digital_input(raw, self.bit_depth_combo.currentData(), self.interface_combo.currentData())
            else:
                raw = apply_analog_input(
                    raw,
                    self.analog_level_combo.currentData(),
                    self.separate_sync_check.isChecked(),
                    self.composite_sync_check.isChecked(),
                    self.sync_on_green_check.isChecked(),
                )
            raw = apply_color_bytes(raw, (spin.value() for spin in self.color_byte_spins))
            raw = apply_feature_flags(
                raw,
                (
                    (0x80, self.standby_check.isChecked()),
                    (0x40, self.suspend_check.isChecked()),
                    (0x20, self.active_off_check.isChecked()),
                    (0x04, self.srgb_check.isChecked()),
                    (0x02, self.preferred_check.isChecked()),
                    (0x01, self.continuous_check.isChecked()),
                ),
            )
            self._structured.raw = raw
            set_text_descriptor(self._structured, 0xFC, self.name_edit.text().strip())
            set_text_descriptor(self._structured, 0xFF, self.serial_edit.text().strip())
            set_text_descriptor(self._structured, 0xFE, self.text_edit.text().strip())
            self._set_range_descriptor()
            self.display_data = self._structured.encode()
            self.dialog.accept()
        except Exception as exc:
            log_exception("Decoded EDID editor apply failed", exc)
            show_message(
                self.dialog,
                key="error_decoded_edid_apply",
                title="Decoded EDID",
                text=str(exc),
                icon=QMessageBox.Icon.Critical,
                label="Decoded EDID apply failure",
            )

    def _set_range_descriptor(self) -> None:
        set_range_descriptor(
            self._structured,
            self.range_min_v.value(),
            self.range_max_v.value(),
            self.range_min_h.value(),
            self.range_max_h.value(),
            self.range_max_clock.value(),
        )
