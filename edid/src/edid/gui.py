from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Callable

from edid.edid_data import EDID_BLOCK_SIZE, DisplayData, DisplayDataError, load_display_data, save_display_data
from edid.edid_library import EdidLibrary, EdidLibraryEntry, content_hash
from edid.logging_utils import log_event, log_exception
from edid.dialog_preferences import DialogPreferencesDialog, show_message, show_yes_no
import edid.ui_loader
from edid.ui.edidcreationwizard import EdidcreationwizardUi
from edid.ui.mainwindow import MainwindowUi
from edid.ui.rawblockeditordialog import RawblockeditordialogUi

try:
    from PySide6.QtCore import QCoreApplication, Qt, QTimer
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QDialog,
        QFileDialog,
        QInputDialog,
        QLineEdit,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QTabWidget,
        QWidget,
        QWizard,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required for GUI mode. Install it with: pip install PySide6") from exc


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Colorlight EDID/DisplayID Tools")
        self.resize(980, 660)

        self._windows_display = None
        self._displays: list[object] = []
        self._hardware_display = None
        self._hardware_displays: list[object] = []
        self._eeprom_unlocked = False
        self._eeprom_user: str | None = None
        self._manager_clipboard: DisplayData | None = None
        self._manager_working_edids: dict[str, DisplayData] = {}
        self._current_data: DisplayData | None = None
        self._last_loaded_path: Path | None = None
        self._edid_library = EdidLibrary()
        self._edids_entries: list[EdidLibraryEntry] = []
        self._display_snapshot_state: tuple[tuple[str, str, str], ...] = ()
        self._display_poll_timer: QTimer | None = None

        self._setup_ui()
        self._init_windows_backend()
        self._init_hardware_backend()
        self._load_cached_eeprom_login()
        self._refresh_displays()
        self._refresh_hardware_displays()
        self._start_display_polling()

    def _setup_ui(self) -> None:
        ui = MainwindowUi(owner=self, window=self)
        root = ui.root
        self.setCentralWidget(root)
        tabs = ui.main_tabs
        if os.name != "nt":
            for tab, label in (
                (ui.override_tab, "Windows Override (unavailable)"),
                (ui.maintenance_tab, "Windows Driver Maintenance (unavailable)"),
            ):
                idx = tabs.indexOf(tab)
                if idx >= 0:
                    tabs.setTabText(idx, label)

        self._bind_main_window_widgets(ui)

        self.status = self.statusBar()
        self.status.showMessage("Ready")
        self._update_eeprom_page()
        self._update_data_buttons()

    def _bind_main_window_widgets(self, ui: MainwindowUi) -> None:
        self.display_combo = ui.display_combo
        self.display_combo.currentIndexChanged.connect(self._on_display_changed)
        self.refresh_button = ui.refresh_button
        self.refresh_button.clicked.connect(self._refresh_displays)
        self.read_active_button = ui.read_active_button
        self.read_active_button.clicked.connect(lambda: self._read_registry_edid("active"))
        self.read_override_button = ui.read_override_button
        self.read_override_button.clicked.connect(lambda: self._read_registry_edid("override"))
        self.save_button = ui.save_button
        self.save_button.clicked.connect(self._save_file)
        self.text_box = ui.text_box
        self.text_box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.decoded_preview_box = ui.decoded_preview_box
        self.current_data_label = ui.current_data_label
        self.load_button = ui.load_button
        self.load_button.clicked.connect(self._load_file)
        self.install_button = ui.install_button
        self.install_button.clicked.connect(self._install_override)
        self.override_remove_button = ui.override_remove_button
        self.override_remove_button.clicked.connect(self._override_remove_installed)
        self.edids_list = ui.edids_list
        self.edids_list.currentRowChanged.connect(self._refresh_edids_selection)
        self.edids_context_banner = ui.edids_context_banner
        self.edids_poll_status_label = ui.edids_poll_status_label
        self.edids_selected_label = ui.edids_selected_label
        self.edids_decoded_box = ui.edids_decoded_box
        self.edids_raw_box = ui.edids_raw_box
        self.edids_raw_box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.edids_preview_tabs = ui.edids_preview_tabs
        self.edids_import_button = ui.edids_import_button
        self.edids_import_button.clicked.connect(self._edids_import_files)
        self.edids_create_button = ui.edids_create_button
        self.edids_create_button.clicked.connect(self._edids_create)
        self.edids_duplicate_button = ui.edids_duplicate_button
        self.edids_duplicate_button.clicked.connect(self._edids_duplicate)
        self.edids_rename_button = ui.edids_rename_button
        self.edids_rename_button.clicked.connect(self._edids_rename)
        self.edids_delete_button = ui.edids_delete_button
        self.edids_delete_button.clicked.connect(self._edids_delete)
        self.edids_export_button = ui.edids_export_button
        self.edids_export_button.clicked.connect(self._edids_export)
        self.edids_read_active_button = ui.edids_read_active_button
        self.edids_read_active_button.clicked.connect(lambda: self._edids_read_selected_display("active"))
        self.edids_read_override_button = ui.edids_read_override_button
        self.edids_read_override_button.clicked.connect(lambda: self._edids_read_selected_display("override"))
        self.manager_selected_combo = ui.manager_selected_combo
        self.manager_selected_combo.currentIndexChanged.connect(self._refresh_manager_edid_lists)
        self.manager_edit_button = ui.manager_edit_button
        self.manager_edit_button.clicked.connect(self._edids_edit_advanced)
        self.manager_refresh_button = ui.manager_refresh_button
        self.manager_refresh_button.clicked.connect(lambda: self._refresh_displays())
        self.eeprom_stack = ui.eeprom_stack
        self.eeprom_email_edit = ui.eeprom_email_edit
        self.eeprom_password_edit = ui.eeprom_password_edit
        self.eeprom_login_button = ui.eeprom_login_button
        self.eeprom_login_button.clicked.connect(self._unlock_eeprom_writer)
        self.eeprom_login_status = ui.eeprom_login_status
        self.hardware_combo = ui.hardware_combo
        self.refresh_hardware_button = ui.refresh_hardware_button
        self.refresh_hardware_button.clicked.connect(self._refresh_hardware_displays)
        self.eeprom_auth_label = ui.eeprom_auth_label
        self.logout_eeprom_button = ui.logout_eeprom_button
        self.logout_eeprom_button.clicked.connect(self._logout_eeprom_writer)
        self.eeprom_load_payload_button = ui.eeprom_load_payload_button
        self.eeprom_load_payload_button.clicked.connect(self._load_file)
        self.eeprom_payload_label = ui.eeprom_payload_label
        self.eeprom_library_combo = ui.eeprom_library_combo
        self.eeprom_load_library_entry_button = ui.eeprom_load_library_entry_button
        self.eeprom_load_library_entry_button.clicked.connect(self._eeprom_load_selected_library_entry)
        self.read_hardware_edid_button = ui.read_hardware_edid_button
        self.read_hardware_edid_button.clicked.connect(lambda: self._read_hardware("edid"))
        self.read_hardware_displayid_button = ui.read_hardware_displayid_button
        self.read_hardware_displayid_button.clicked.connect(lambda: self._read_hardware("displayid"))
        self.write_hardware_edid_button = ui.write_hardware_edid_button
        self.write_hardware_edid_button.clicked.connect(lambda: self._write_hardware("edid"))
        self.write_hardware_displayid_button = ui.write_hardware_displayid_button
        self.write_hardware_displayid_button.clicked.connect(lambda: self._write_hardware("displayid"))
        self.hardware_backend_label = ui.hardware_backend_label
        self.maintenance_display_combo = ui.maintenance_display_combo
        self.reset_selected_button = ui.reset_selected_button
        self.reset_selected_button.clicked.connect(self._reset_selected)
        self.reset_all_button = ui.reset_all_button
        self.reset_all_button.clicked.connect(self._reset_all)
        self.restart_button = ui.restart_button
        self.restart_button.clicked.connect(self._restart_driver)
        self.recovery_restart_button = ui.recovery_restart_button
        self.recovery_restart_button.clicked.connect(self._recovery_restart_driver)
        self._set_hardware_controls_enabled(False)
        self._layout_ui = ui
        self._refresh_edids_library()

    def _refresh_library_combos(self) -> None:
        if not hasattr(self, "eeprom_library_combo"):
            return
        combo = self.eeprom_library_combo
        combo.blockSignals(True)
        prev = combo.currentData()
        combo.clear()
        combo.addItem("— choose library profile —", "")
        for entry in self._edids_entries:
            combo.addItem(f"{entry.name}  ({entry.size} bytes)", entry.id)
        if prev:
            idx = combo.findData(prev)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _eeprom_load_selected_library_entry(self) -> None:
        combo = self.eeprom_library_combo
        entry_id = combo.currentData()
        title = "EEPROM"
        if not entry_id:
            self._warn("Choose a library profile in the drop-down first.", title=title)
            return
        try:
            data = self._edid_library.load(str(entry_id))
        except Exception as exc:
            self._error(exc, title=title)
            return
        if self._process_loaded_data(data.clone(), title=f"{title} — load from library"):
            self.status.showMessage(f"Loaded library profile into the shared working copy ({title}).")

    def _show_preferences(self) -> None:
        DialogPreferencesDialog(self).exec()

    def _init_windows_backend(self) -> None:
        try:
            from edid import windows_display

            self._windows_display = windows_display
        except Exception as exc:
            log_exception("Windows backend initialization failed", exc)
            self._windows_display = None
            self._set_windows_controls_enabled(False)
            self._warn(str(exc), title="Windows Backend Unavailable")

    def _init_hardware_backend(self) -> None:
        try:
            from edid import hardware_display

            self._hardware_display = hardware_display
        except Exception as exc:
            log_exception("Hardware backend initialization failed", exc)
            self._hardware_display = None
            self._set_hardware_controls_enabled(False)
            self._warn(str(exc), title="Hardware Backend Unavailable")

    def _load_cached_eeprom_login(self) -> None:
        try:
            from edid.issue_tracker_auth import load_cached_auth

            cached = load_cached_auth()
        except Exception as exc:
            log_exception("EEPROM cached login load failed", exc)
            cached = None
        if cached and cached.ok:
            self._set_eeprom_logged_in(cached.email or cached.name or "approved user")

    def _set_eeprom_logged_in(self, user: str | None) -> None:
        self._eeprom_unlocked = True
        self._eeprom_user = user
        self.eeprom_auth_label.setText(f"Unlocked for {user or 'approved user'}. EEPROM reads/writes are enabled.")
        self.eeprom_stack.setCurrentIndex(1)
        self._set_hardware_controls_enabled(True)
        self._refresh_hardware_displays()

    def _update_eeprom_page(self) -> None:
        self.eeprom_stack.setCurrentIndex(1 if self._eeprom_unlocked else 0)

    def _set_windows_controls_enabled(self, enabled: bool) -> None:
        for control in (
            self.display_combo,
            self.refresh_button,
            self.read_active_button,
            self.read_override_button,
            self.install_button,
            self.override_remove_button,
            self.reset_selected_button,
            self.reset_all_button,
            self.restart_button,
            self.recovery_restart_button,
            self.manager_selected_combo,
            self.manager_refresh_button,
            self.edids_read_active_button,
            self.edids_read_override_button,
        ):
            control.setEnabled(enabled)

    def _set_hardware_controls_enabled(self, enabled: bool) -> None:
        for control in (
            self.hardware_combo,
            self.refresh_hardware_button,
            self.read_hardware_edid_button,
            self.read_hardware_displayid_button,
            self.write_hardware_edid_button,
            self.write_hardware_displayid_button,
        ):
            control.setEnabled(enabled)

    def _refresh_displays(self, preferred_key: str | None = None, *, background: bool = False) -> None:
        if self._windows_display is None:
            return
        preferred_key = preferred_key or self._current_display_key()
        try:
            self._displays = self._windows_display.list_display_instances()
        except Exception as exc:
            self._displays = []
            if background:
                self.edids_poll_status_label.setText(f"Display polling failed: {exc}")
                log_exception("Display polling failed", exc)
            else:
                self._error(exc, title="List Displays")
        self.display_combo.blockSignals(True)
        self.display_combo.clear()
        if not self._displays:
            self.display_combo.addItem("No displays found")
        else:
            for item in self._displays:
                self.display_combo.addItem(item.label(), item.key)
            if preferred_key:
                index = self.display_combo.findData(preferred_key)
                if index >= 0:
                    self.display_combo.setCurrentIndex(index)
                elif self.display_combo.count() > 0:
                    self.display_combo.setCurrentIndex(0)
        self.display_combo.blockSignals(False)
        self._on_display_changed()
        self._sync_manager_selection(preferred_key)
        # Keep display state current for polling, but avoid automatic library backups.
        self._display_snapshot_state = self._display_state(self._displays)
        if not background:
            self.edids_poll_status_label.setText(
                "Display list refreshed. Use Pull active / Pull override to snapshot monitor data."
            )

    def _start_display_polling(self) -> None:
        if self._windows_display is None:
            return
        self._display_poll_timer = QTimer(self)
        self._display_poll_timer.setInterval(5000)
        self._display_poll_timer.timeout.connect(self._poll_display_changes)
        self._display_poll_timer.start()
        self.edids_poll_status_label.setText(
            "Automatic polling is on: display changes are detected, but snapshots are only saved manually."
        )

    def _poll_display_changes(self) -> None:
        if self._windows_display is None:
            return
        try:
            displays = self._windows_display.list_display_instances()
        except Exception as exc:
            self.edids_poll_status_label.setText(f"Display polling failed: {exc}")
            log_exception("Display polling failed", exc)
            return
        state = self._display_state(displays)
        if state == self._display_snapshot_state:
            return
        preferred_key = self._current_display_key()
        self._displays = displays
        self._refresh_display_combos(preferred_key)
        self._display_snapshot_state = state
        self.edids_poll_status_label.setText(
            "Monitor change detected. Use Pull active / Pull override to snapshot updated data."
        )

    def _refresh_display_combos(self, preferred_key: str | None = None) -> None:
        self.display_combo.blockSignals(True)
        self.display_combo.clear()
        if not self._displays:
            self.display_combo.addItem("No displays found")
        else:
            for item in self._displays:
                self.display_combo.addItem(item.label(), item.key)
            if preferred_key:
                index = self.display_combo.findData(preferred_key)
                if index >= 0:
                    self.display_combo.setCurrentIndex(index)
        self.display_combo.blockSignals(False)
        self._on_display_changed()
        self._sync_manager_selection(preferred_key)

    def _display_state(self, displays: list[object]) -> tuple[tuple[str, str, str], ...]:
        state: list[tuple[str, str, str]] = []
        for display in displays:
            active_data = getattr(display, "active_data", None)
            override_data = getattr(display, "override_data", None)
            state.append(
                (
                    str(getattr(display, "key", "")),
                    content_hash(active_data) if isinstance(active_data, DisplayData) else "",
                    content_hash(override_data) if isinstance(override_data, DisplayData) else "",
                )
            )
        return tuple(sorted(state))

    def _snapshot_display_data(self, display: object, source: str, data: DisplayData) -> EdidLibraryEntry:
        disp = getattr(display, "name", "Display") or "Display"
        layer = "Effective / active chain" if source == "active" else "Windows registry override"
        source_label = f"{disp} — {layer}"
        profile_name = self._snapshot_resolution_name(data, source)
        return self._edid_library.upsert_snapshot(
            data,
            source_kind=f"display_{source}",
            display_key=str(getattr(display, "key", "")),
            device_id=str(getattr(display, "device_id", "")),
            instance_id=str(getattr(display, "instance_id", "")),
            source_label=source_label,
            name=profile_name,
        )

    def _snapshot_resolution_name(self, data: DisplayData, source: str) -> str:
        """Human-first snapshot name: prefer the EDID's own display name."""
        layer = "active" if source == "active" else "override"
        edid_name = data.name()
        mode_label = ""
        if data.is_edid:
            try:
                from edid.structured_edid import StructuredEDID

                structured = StructuredEDID.parse(data)
                timing = structured.preferred_timing() or next(
                    (item for item in structured.detailed_timings if item.h_active > 0 and item.v_active > 0),
                    None,
                )
                if timing is not None:
                    refresh = timing.refresh_rate
                    if refresh is None:
                        mode_label = f"{timing.h_active}x{timing.v_active}"
                    else:
                        mode_label = f"{timing.h_active}x{timing.v_active}@{refresh:.0f}Hz"
            except Exception as exc:
                log_exception("Snapshot EDID resolution naming failed", exc)
        if edid_name:
            suffix = f", {mode_label}" if mode_label else ""
            return f"{edid_name} ({layer}{suffix})"
        fallback = data.product_id() or data.type_name
        suffix = f", {mode_label}" if mode_label else ""
        return f"{fallback} ({layer}{suffix})"

    def _current_display_key(self) -> str | None:
        if hasattr(self, "display_combo"):
            key = self.display_combo.currentData()
            if key:
                return str(key)
        display = self._selected_display()
        return display.key if display else None

    def _sync_manager_selection(self, preferred_key: str | None = None) -> None:
        if not hasattr(self, "manager_selected_combo"):
            return
        current_key = preferred_key or self.manager_selected_combo.currentData()
        self.manager_selected_combo.blockSignals(True)
        self.manager_selected_combo.clear()
        for display in self._displays:
            self.manager_selected_combo.addItem(display.label(), display.key)
        if hasattr(self, "maintenance_display_combo"):
            maintenance_key = self.maintenance_display_combo.currentData()
            self.maintenance_display_combo.blockSignals(True)
            self.maintenance_display_combo.clear()
            for display in self._displays:
                self.maintenance_display_combo.addItem(display.label(), display.key)
            wanted = preferred_key or maintenance_key
            if wanted:
                index = self.maintenance_display_combo.findData(wanted)
                if index >= 0:
                    self.maintenance_display_combo.setCurrentIndex(index)
            self.maintenance_display_combo.blockSignals(False)
        if current_key:
            index = self.manager_selected_combo.findData(current_key)
            if index >= 0:
                self.manager_selected_combo.setCurrentIndex(index)
        self.manager_selected_combo.blockSignals(False)
        self._refresh_manager_edid_lists()

    def _refresh_monitor_manager(self, preferred_key: str | None = None) -> None:
        if not hasattr(self, "manager_selected_combo"):
            return
        preferred_key = preferred_key or self._current_display_key()
        if self._windows_display is None:
            self._update_edids_context_banner()
            return
        try:
            self._displays = self._windows_display.list_display_instances()
        except Exception as exc:
            self._error(exc, title="EDID library")
            self._update_edids_context_banner()
            return
        self._sync_manager_selection(preferred_key)

    def _manager_current_key(self) -> str | None:
        if not hasattr(self, "manager_selected_combo"):
            return None
        key = self.manager_selected_combo.currentData()
        return str(key) if key else None

    def _manager_current_edid_data(self) -> DisplayData | None:
        key = self._manager_current_key()
        if key and key in self._manager_working_edids:
            return self._manager_working_edids[key]
        display = self._manager_selected_display()
        if not display:
            return None
        return display.override_data or display.active_data

    def _refresh_manager_edid_lists(self, *_args: object) -> None:
        if not hasattr(self, "manager_selected_combo"):
            return
        self._update_edids_context_banner()

    def _refresh_hardware_displays(self) -> None:
        if not self._eeprom_unlocked or self._hardware_display is None:
            return
        try:
            statuses = self._hardware_display.hardware_backend_status()
            self.hardware_backend_label.setText(
                "\n".join(
                    f"{status.backend}: {'available' if status.available else 'unavailable'} ({status.display_count} display(s)) - {status.message}"
                    for status in statuses
                )
            )
            self._hardware_displays = self._hardware_display.list_hardware_displays()
        except Exception as exc:
            self._hardware_displays = []
            self._error(exc, title="List Hardware Displays")
        self.hardware_combo.clear()
        if not self._hardware_displays:
            self.hardware_combo.addItem("No hardware DDC displays found")
        else:
            for item in self._hardware_displays:
                self.hardware_combo.addItem(item.label())
        self._update_data_buttons()

    def _unlock_eeprom_writer(self) -> None:
        email = self.eeprom_email_edit.text().strip()
        password = self.eeprom_password_edit.text()
        if not email or not password:
            self.eeprom_login_status.setText("Email and password are required.")
            return
        try:
            from edid.issue_tracker_auth import authenticate_issue_tracker_user, save_cached_auth

            result = authenticate_issue_tracker_user(email, password)
        except Exception as exc:
            self.eeprom_login_status.setText(str(exc))
            return
        if not result.ok:
            self.eeprom_login_status.setText(result.error or "Invalid credentials or account is not approved.")
            return
        save_cached_auth(result)
        self.eeprom_password_edit.clear()
        self._set_eeprom_logged_in(result.email or result.name or email)

    def _logout_eeprom_writer(self) -> None:
        try:
            from edid.issue_tracker_auth import clear_cached_auth

            clear_cached_auth()
        except Exception as exc:
            log_exception("EEPROM cached login clear failed", exc)
        self._eeprom_unlocked = False
        self._eeprom_user = None
        self._hardware_displays = []
        self.hardware_combo.clear()
        self._set_hardware_controls_enabled(False)
        self._update_eeprom_page()
        self._update_data_buttons()

    def _selected_display(self) -> object | None:
        index = self.display_combo.currentIndex()
        if index < 0 or index >= len(self._displays):
            return None
        return self._displays[index]

    def _manager_selected_display(self) -> object | None:
        key = self.manager_selected_combo.currentData()
        for display in self._displays:
            if display.key == key:
                return display
        return None

    def _selected_hardware_display(self) -> object | None:
        index = self.hardware_combo.currentIndex()
        if index < 0 or index >= len(self._hardware_displays):
            return None
        return self._hardware_displays[index]

    def _on_display_changed(self) -> None:
        display = self._selected_display()
        self.status.showMessage("No display selected" if display is None else display.label())
        self._update_data_buttons()

    def _load_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Load EDID/DisplayID file",
            "",
            "EDID files (*.bin *.dat *.txt *.inf);;All files (*.*)",
        )
        if not file_name:
            return
        try:
            if self._process_loaded_data(load_display_data(file_name, trim=False), title="Load File"):
                self._last_loaded_path = Path(file_name)
                self.status.showMessage(f"Loaded: {file_name}")
        except Exception as exc:
            self._error(exc, title="Load File")

    def _save_file(self) -> None:
        if not self._current_data:
            return
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save EDID/DisplayID file",
            str(self._last_loaded_path) if self._last_loaded_path else "",
            "BIN (*.bin);;DAT (*.dat);;TXT (*.txt);;INF (*.inf)",
        )
        if not file_name:
            return
        fmt = "auto"
        for name, value in (("BIN", "bin"), ("DAT", "dat"), ("TXT", "txt"), ("INF", "inf")):
            if name in selected_filter:
                fmt = value
        try:
            self._auto_repair_current_data()
            save_display_data(self._current_data, file_name, fmt)
            self.status.showMessage(f"Saved: {file_name}")
        except Exception as exc:
            self._error(exc, title="Save File")

    def _refresh_edids_library(self, select_id: str | None = None) -> None:
        current_entry = self._edids_selected_entry()
        selected_id = select_id or (current_entry.id if current_entry else None)
        try:
            self._edids_entries = self._edid_library.list_entries()
        except Exception as exc:
            self._error(exc, title="Library")
            self._edids_entries = []
        self.edids_list.blockSignals(True)
        self.edids_list.clear()
        selected_row = -1
        for row, entry in enumerate(self._edids_entries):
            item = QListWidgetItem(f"{entry.name}  •  {entry.size} bytes")
            item.setToolTip(_library_row_tooltip(entry))
            item.setData(Qt.UserRole, entry.id)
            self.edids_list.addItem(item)
            if entry.id == selected_id:
                selected_row = row
        if selected_row < 0 and self._edids_entries:
            selected_row = 0
        if selected_row >= 0:
            self.edids_list.setCurrentRow(selected_row)
        self.edids_list.blockSignals(False)
        self._refresh_library_combos()
        self._refresh_edids_selection()

    def _edids_focus_decoded_tab(self) -> None:
        tabs = getattr(self, "edids_preview_tabs", None)
        if isinstance(tabs, QTabWidget) and tabs.count() > 0:
            tabs.setCurrentIndex(0)

    def _refresh_edids_selection(self) -> None:
        entry = self._edids_selected_entry()
        if not entry:
            self.edids_selected_label.setText("No saved file selected.")
            self.edids_decoded_box.setPlainText("")
            self.edids_raw_box.setPlainText("")
            self._update_edids_buttons(None)
            self._update_edids_context_banner()
            return
        data = self._edids_load_entry_data(entry)
        if not data:
            self._update_edids_buttons(None)
            self._update_edids_context_banner()
            return
        self.edids_selected_label.setText(f"{entry.name} - {entry.type_name}, {entry.size} bytes")
        self.edids_decoded_box.setPlainText(self._decoded_data_text(data))
        self.edids_raw_box.setPlainText(data.to_text())
        self._update_edids_buttons(data)
        self._update_edids_context_banner()

    def _edids_read_selected_display(self, source: str) -> None:
        display = self._manager_selected_display()
        if not display:
            self._warn("No connected display is selected.", title="Library and live editor")
            return
        data = display.override_data if source == "override" else display.active_data
        if data is None:
            self._warn(f"Selected display has no {source} EDID.", title="Library and live editor")
            return
        entry = self._snapshot_display_data(display, source, data)
        if self._process_loaded_data(data.clone(), title=f"Read {source.capitalize()} EDID"):
            self._refresh_edids_library(entry.id)
            self._edids_focus_decoded_tab()
            self.status.showMessage(f"Read and backed up selected display {source} EDID.")

    def _edids_import_files(self) -> None:
        file_names, _ = QFileDialog.getOpenFileNames(
            self,
            "Import EDID/DisplayID files",
            "",
            "EDID files (*.bin *.dat *.txt *.inf);;All files (*.*)",
        )
        if not file_names:
            return
        imported: list[EdidLibraryEntry] = []
        try:
            for file_name in file_names:
                imported.append(self._edid_library.import_file(file_name))
            self._refresh_edids_library(imported[-1].id if imported else None)
            self.status.showMessage(f"Imported {len(imported)} EDID file(s) into the library.")
        except Exception as exc:
            self._refresh_edids_library(imported[-1].id if imported else None)
            self._error(exc, title="Import library")

    def _edids_create(self) -> None:
        dialog = EdidCreationWizard(self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            entry = self._edid_library.save_new(
                dialog.display_data,
                name=dialog.display_data.name() or "Created EDID",
            )
            self._current_data = dialog.display_data.clone()
            self._refresh_textbox()
            self._refresh_edids_library(entry.id)
            self.status.showMessage("Created a new EDID profile and saved it to the library.")
            if dialog.open_advanced_editor:
                if self._open_typed_editors() and self._current_data:
                    entry = self._edid_library.update_data(
                        entry.id,
                        self._current_data,
                        name=self._current_data.name() or entry.name,
                    )
                    self._refresh_edids_library(entry.id)
                    self.status.showMessage("Advanced EDID edits saved to the library entry.")
            should_export = show_yes_no(
                self,
                key="confirm_export_new_profile",
                title="Export new profile",
                text="Export this new library entry to a BIN/DAT/TXT/INF file now?\n\n"
                "You can always export later using Export.",
                default=QMessageBox.StandardButton.Yes,
                label="Create EDID: prompt to export new profile",
            )
            if should_export:
                self._edids_prompt_export_library_entry(entry)
        except Exception as exc:
            self._error(exc, title="Create EDID")

    def _edids_duplicate(self) -> None:
        entry = self._edids_selected_entry()
        if not entry:
            return
        try:
            copy_entry = self._edid_library.duplicate(entry.id)
            self._refresh_edids_library(copy_entry.id)
            self.status.showMessage("EDID library entry duplicated.")
        except Exception as exc:
            self._error(exc, title="Duplicate EDID")

    def _edids_rename(self) -> None:
        entry = self._edids_selected_entry()
        if not entry:
            return
        name, accepted = QInputDialog.getText(self, "Rename EDID", "Library name:", QLineEdit.Normal, entry.name)
        if not accepted:
            return
        try:
            renamed = self._edid_library.rename(entry.id, name)
            self._refresh_edids_library(renamed.id)
            self.status.showMessage("EDID library entry renamed.")
        except Exception as exc:
            self._error(exc, title="Rename EDID")

    def _edids_delete(self) -> None:
        entry = self._edids_selected_entry()
        if not entry:
            return
        if not self._confirm(f"Delete '{entry.name}' from the library?", title="Delete EDID"):
            return
        try:
            self._edid_library.delete(entry.id)
            self._refresh_edids_library()
            self.status.showMessage("EDID library entry deleted.")
        except Exception as exc:
            self._error(exc, title="Delete EDID")

    def _edids_edit_advanced(self) -> None:
        entry = self._edids_selected_entry()
        data = self._edids_load_entry_data(entry) if entry else None
        if not entry or not data:
            return
        self._current_data = data
        self._refresh_textbox()
        if self._open_typed_editors() and self._current_data:
            updated = self._edid_library.update_data(
                entry.id,
                self._current_data,
                name=self._current_data.name() or entry.name,
            )
            self._refresh_edids_library(updated.id)
            self.status.showMessage("Advanced EDID edits saved to the library.")

    def _edids_edit_raw(self) -> None:
        entry = self._edids_selected_entry()
        data = self._edids_load_entry_data(entry) if entry else None
        if not entry or not data:
            return
        self._current_data = data
        self._refresh_textbox()
        if self._open_block_editor() and self._current_data:
            updated = self._edid_library.update_data(entry.id, self._current_data)
            self._refresh_edids_library(updated.id)
            self.status.showMessage("Raw EDID block edits saved to the library.")

    def _edids_set_current(self) -> None:
        entry = self._edids_selected_entry()
        if entry and self._edids_set_entry_as_current(entry, title="Library", status="Selected file is now the shared working copy."):
            self._last_loaded_path = None

    def _edids_export(self) -> None:
        entry = self._edids_selected_entry()
        if not entry:
            return
        self._edids_prompt_export_library_entry(entry)

    def _edids_prompt_export_library_entry(self, entry: EdidLibraryEntry) -> None:
        data = self._edids_load_entry_data(entry)
        if not data:
            return
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export EDID/DisplayID file",
            f"{_safe_file_stem(entry.name)}.bin",
            "BIN (*.bin);;DAT (*.dat);;TXT (*.txt);;INF (*.inf)",
        )
        if not file_name:
            return
        fmt = "auto"
        for name, value in (("BIN", "bin"), ("DAT", "dat"), ("TXT", "txt"), ("INF", "inf")):
            if name in selected_filter:
                fmt = value
        try:
            save_display_data(data.auto_fix(), file_name, fmt)
            self.status.showMessage(f"Exported EDID library entry to {file_name}")
        except Exception as exc:
            self._error(exc, title="Export EDID")

    def _edids_send_override(self) -> None:
        entry = self._edids_selected_entry()
        if entry and self._edids_set_entry_as_current(entry, title="Send To Windows Override", status="Selected EDID loaded for Windows override."):
            self._install_override()

    def _edids_set_entry_as_current(self, entry: EdidLibraryEntry, *, title: str, status: str) -> bool:
        data = self._edids_load_entry_data(entry)
        if not data:
            return False
        if not self._process_loaded_data(data, title=title):
            return False
        self.status.showMessage(status)
        return True

    def _update_edids_context_banner(self) -> None:
        if not getattr(self, "edids_context_banner", None):
            return
        mgr_key = self._manager_current_key()
        if not hasattr(self, "manager_selected_combo") or self.manager_selected_combo.count() == 0:
            monitor_text = "Monitor list not loaded yet."
        else:
            display_name = (self.manager_selected_combo.currentText() or "Selected monitor").strip()
            if not getattr(self, "_displays", []):
                monitor_text = "No connected displays."
            elif not mgr_key:
                monitor_text = f"{display_name} — pick a monitor in the list when available."
            else:
                data = self._manager_current_edid_data()
                using_working = bool(mgr_key in self._manager_working_edids)
                if data is None:
                    monitor_text = (
                        f"{display_name} — no capability bytes yet "
                        "(use Pull active / Pull override, or read from the Windows Override tab)."
                    )
                elif not data.is_edid:
                    monitor_text = (
                        f"{display_name} — payload is not classic EDID (e.g. DisplayID only); "
                        "decoded views may be sparse."
                    )
                elif using_working:
                    monitor_text = (
                        f"{display_name} — unsaved local working copy in memory; "
                        "install a Windows override when ready."
                    )
                else:
                    monitor_text = (
                        f"{display_name} — live effective-chain view "
                        "(not the optional registry override layer alone)."
                    )

        entry = self._edids_selected_entry()
        if not entry:
            library_text = "No library row selected — choose a row to see Decoded / Raw on the right."
        else:
            library_text = f'Library row: "{entry.name}". Use Decoded for a full structure readout.'

        note = ""
        if entry and mgr_key:
            ek = entry.display_key
            if ek is None:
                note = " (This file is not tied to the monitor above—common for imports.)"
            elif ek != mgr_key:
                note = " (This file is linked to a different monitor than the one above.)"

        self.edids_context_banner.setText(f"{monitor_text} {library_text}{note}")

    def _edids_selected_entry(self) -> EdidLibraryEntry | None:
        item = self.edids_list.currentItem() if hasattr(self, "edids_list") else None
        entry_id = item.data(Qt.UserRole) if item else None
        for entry in self._edids_entries:
            if entry.id == entry_id:
                return entry
        return None

    def _edids_load_entry_data(self, entry: EdidLibraryEntry | None) -> DisplayData | None:
        if not entry:
            return None
        try:
            return self._edid_library.load(entry.id)
        except Exception as exc:
            self._error(exc, title="Library")
            return None

    def _read_registry_edid(self, source: str) -> None:
        if self._windows_display is None:
            return
        display = self._selected_display()
        if display is None:
            return
        try:
            self._process_loaded_data(self._windows_display.export_display_data(display.key, source=source), title=f"Read {source.capitalize()} EDID")
        except Exception as exc:
            self._error(exc, title=f"Read {source.capitalize()} EDID")

    def _manager_load_selected(self, source: str) -> None:
        display = self._manager_selected_display()
        if not display:
            return
        data = display.override_data if source == "override" else display.active_data
        if data is None:
            self._warn(f"Selected monitor has no {source} EDID.", title="EDID library")
            return
        if self._process_loaded_data(data, title=f"Load {source.capitalize()} EDID"):
            self._manager_working_edids[display.key] = data.clone()
            self._refresh_manager_edid_lists()

    def _manager_edit_selected(self) -> None:
        data = self._manager_current_edid_data()
        if not data:
            self._warn("Selected monitor has no EDID data to edit.", title="EDID library")
            return
        display = self._manager_selected_display()
        if self._process_loaded_data(data, title="Edit Monitor EDID") and self._open_typed_editors():
            if display and self._current_data:
                self._manager_working_edids[display.key] = self._current_data.clone()
            self._refresh_manager_edid_lists()

    def _manager_copy_selected(self) -> None:
        data = self._manager_current_edid_data()
        if not data:
            self._warn("Selected monitor has no EDID data to copy.", title="EDID library")
            return
        self._manager_clipboard = data.clone()
        self.status.showMessage("Monitor EDID copied. Choose another monitor and use Paste to install it as an override.")

    def _manager_paste_to_selected(self) -> None:
        if self._windows_display is None or not self._manager_clipboard:
            return
        display = self._manager_selected_display()
        if not display:
            return
        if not self._confirm(f"Install copied EDID as an override for {display.name}?", title="EDID library"):
            return
        try:
            self._windows_display.install_edid_override(self._manager_clipboard, target=display.key, allow_invalid=True)
            self._manager_working_edids.pop(display.key, None)
            self._refresh_displays(display.key)
            self._refresh_monitor_manager(display.key)
            self.status.showMessage("Copied EDID installed as override.")
        except Exception as exc:
            self._error(exc, title="EDID library")

    def _manager_working_structured(self):
        data = self._manager_current_edid_data()
        if not data:
            return None
        try:
            from edid.structured_edid import StructuredEDID

            return StructuredEDID.parse(data)
        except Exception as exc:
            self._error(exc, title="EDID library")
            return None

    def _manager_apply_structured(self, structured: object, message: str) -> None:
        try:
            display = self._manager_selected_display()
            encoded = structured.encode()
            if display:
                self._manager_working_edids[display.key] = encoded.clone()
                self._log(
                    "Stored working EDID",
                    key=display.key,
                    bytes=encoded.size,
                    extensions=len(structured.extensions),
                )
            self._current_data = encoded
            self._refresh_textbox()
            self._refresh_manager_edid_lists()
            self.status.showMessage(f"{message} Working EDID updated. Install it as an override to apply to Windows.")
        except Exception as exc:
            self._error(exc, title="EDID library")

    def _manager_export_selected(self, source: str) -> None:
        display = self._manager_selected_display()
        if not display:
            return
        data = display.override_data if source == "override" else display.active_data
        if data is None:
            self._warn(f"Selected monitor has no {source} EDID.", title="EDID library")
            return
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            f"Export {source.capitalize()} EDID",
            f"{display.product_id or 'monitor'}-{source}.bin",
            "BIN (*.bin);;DAT (*.dat);;TXT (*.txt);;INF (*.inf)",
        )
        if not file_name:
            return
        fmt = "auto"
        for name, value in (("BIN", "bin"), ("DAT", "dat"), ("TXT", "txt"), ("INF", "inf")):
            if name in selected_filter:
                fmt = value
        try:
            save_display_data(data, file_name, fmt)
            self.status.showMessage(f"Exported {source} EDID to {file_name}")
        except Exception as exc:
            self._error(exc, title="Export EDID")

    def _manager_remove_selected_override(self) -> None:
        if self._windows_display is None:
            return
        display = self._manager_selected_display()
        if not display:
            return
        if not display.has_override:
            self._warn("Selected monitor has no override to remove.", title="EDID library")
            return
        if not self._confirm(f"Remove EDID override for {display.name}?", title="EDID library"):
            return
        try:
            self._windows_display.reset_display(display.key)
            self._manager_working_edids.pop(display.key, None)
            self._refresh_displays(display.key)
            self._refresh_monitor_manager(display.key)
            self.status.showMessage("Override removed.")
        except Exception as exc:
            self._error(exc, title="EDID library")

    def _manager_delete_selected_monitor_data(self) -> None:
        if self._windows_display is None:
            return
        display = self._manager_selected_display()
        if not display:
            return
        self._log(
            "Clear monitor override data requested",
            key=display.key,
            device_id=display.device_id,
            instance_id=display.instance_id,
            admin=self._windows_display.is_admin(),
        )
        message = (
            f"Clear override data for {display.name}?\n\n"
            f"{display.key}\n\n"
            "This removes only EDID_OVERRIDE and EDID_RECOVERY values for this monitor. "
            "It preserves the active EDID cache and does not delete the protected Plug and Play device instance key."
        )
        if not self._confirm(message, title="Clear Override Data"):
            self._log("Clear monitor override data cancelled", key=display.key)
            return
        try:
            self._windows_display.reset_display(display.key)
            self._log("Clear monitor override data succeeded", key=display.key)
            self._manager_working_edids.pop(display.key, None)
            self._refresh_displays(display.key)
            self._refresh_monitor_manager(display.key)
            self.status.showMessage("Monitor override data cleared. Active EDID was preserved.")
        except Exception as exc:
            self._log("Clear monitor override data failed", key=display.key, error=exc)
            self._error(exc, title="Clear Override Data")

    def _process_loaded_data(self, data: DisplayData, *, title: str) -> bool:
        selected = self._selected_display()
        incoming_id = data.product_id()
        selected_id = selected.product_id if selected else None
        if incoming_id and selected_id and len(incoming_id) == len(selected_id) and incoming_id != selected_id:
            if not self._confirm(f"Product ID does not match selected display ({incoming_id} vs {selected_id}). Load anyway?", title=title):
                return False
        self._current_data = data
        self._refresh_textbox()
        warnings = data.warnings()
        if warnings:
            self._warn("\n".join(warnings), title=title)
        return True

    def _refresh_textbox(self) -> None:
        self.text_box.setPlainText("No data" if not self._current_data else self._current_data.to_text())
        if not self._current_data:
            self.current_data_label.setText(
                "Nothing loaded yet. Read from the monitor, load a library row on the Library and live editor tab, or use File → Load."
            )
            self.decoded_preview_box.setPlainText("")
        else:
            name = self._current_data.name() or "unknown display"
            product = self._current_data.product_id() or "unknown product"
            warnings = self._current_data.warnings()
            warning_text = f" {len(warnings)} warning(s) found." if warnings else " Checksums and structure look OK."
            self.current_data_label.setText(
                f"Loaded {self._current_data.type_name}: {name} ({product}), {self._current_data.size} bytes.{warning_text}"
            )
            self.decoded_preview_box.setPlainText(self._decoded_preview_text())
        self._refresh_eeprom_payload_label()
        self._update_data_buttons()

    def _refresh_eeprom_payload_label(self) -> None:
        if not self._current_data:
            self.eeprom_payload_label.setText(
                "Nothing loaded for EEPROM writes. Choose a library entry above, load from file, read from hardware, or File → Load (one shared working copy)."
            )
        else:
            name = self._current_data.name() or "unknown display"
            product = self._current_data.product_id() or "unknown product"
            self.eeprom_payload_label.setText(
                f"Payload for writes: {self._current_data.type_name}, {self._current_data.size} bytes — {name} ({product})."
            )

    def _decoded_preview_text(self) -> str:
        if not self._current_data:
            return ""
        return self._decoded_data_text(self._current_data)

    def _decoded_data_text(self, data: DisplayData) -> str:
        try:
            from edid.edid_decode_text import decode_display_data

            return decode_display_data(data, include_hex=False)
        except Exception as exc:
            log_exception("Decoded preview failed", exc)
            return f"Could not decode data:\n{exc}"

    def _auto_repair_current_data(self) -> None:
        if not self._current_data:
            return
        repaired = self._current_data.auto_fix()
        if repaired.data != self._current_data.data:
            self._current_data = repaired
            self._refresh_textbox()

    def _show_about(self) -> None:
        show_message(
            self,
            key="info_about_dialog",
            title="About Colorlight EDID/DisplayID Tools",
            text="Colorlight EDID/DisplayID Tools\n\n"
            "Display override editor and EEPROM writer.\n\n"
            "Contact: daniel.gleason@lednets.com",
            icon=QMessageBox.Icon.Information,
            label="About dialog",
        )

    def _open_typed_editors(self) -> bool:
        if not self._current_data:
            return False
        try:
            from edid.gui_editors import TypedEditorDialog, WorkflowEditorDialog

            try:
                dialog = WorkflowEditorDialog(self._current_data, self, beginner_mode=True)
            except Exception:
                dialog = TypedEditorDialog(self._current_data, self)
            if dialog.exec() == QDialog.Accepted:
                self._current_data = dialog.display_data
                self._refresh_textbox()
                return True
        except Exception as exc:
            self._error(exc, title="Typed Editors")
        return False

    def _open_block_editor(self) -> bool:
        if not self._current_data or not self._current_data.is_edid:
            return False
        dialog = RawBlockEditorDialog(self._current_data, self)
        if dialog.exec() == QDialog.Accepted:
            self._current_data = dialog.display_data
            self._refresh_textbox()
            return True
        return False

    def _install_override(self) -> None:
        if self._windows_display is None or not self._current_data:
            return
        if not self._windows_display.is_admin():
            self._warn("Administrator privileges are required. Start the app with run_edid_app.bat to launch elevated.", title="Install Override")
            return
        display = self._selected_display()
        if display is None or not self._confirm("Install EDID override for selected display?", title="Install Override"):
            return
        try:
            self._auto_repair_current_data()
            self._windows_display.install_edid_override(self._current_data, target=display.key)
            self.status.showMessage("Override installed. Restart driver or reboot to apply.")
            self._refresh_displays(display.key)
        except Exception as exc:
            self._error(exc, title="Install Override")

    def _override_remove_installed(self) -> None:
        if self._windows_display is None:
            return
        if not self._windows_display.is_admin():
            self._warn("Administrator privileges are required. Start the app with run_edid_app.bat to launch elevated.", title="Remove Override")
            return
        display = self._selected_display()
        if not display:
            self._warn("Choose a display in Step 1.", title="Remove Override")
            return
        if not display.has_override:
            self._warn("The selected display has no installed EDID override to remove.", title="Remove Override")
            return
        if not self._confirm(
            f'Remove the Windows EDID override for "{display.name}"?\n\n'
            "Windows will use the monitor's built-in EDID again after redetection. "
            "Restart the display driver or reboot if the change does not apply immediately.",
            title="Remove Override",
        ):
            return
        try:
            self._windows_display.reset_display(display.key)
            self._manager_working_edids.pop(display.key, None)
            self._refresh_displays(display.key)
            self._refresh_monitor_manager(display.key)
            self.status.showMessage("EDID override removed for the selected display.")
        except Exception as exc:
            self._error(exc, title="Remove Override")

    def _read_hardware(self, kind: str) -> None:
        if not self._eeprom_unlocked:
            return
        display = self._selected_hardware_display()
        if display is None:
            return
        try:
            data = display.read_displayid() if kind == "displayid" else display.read_edid()
            self._process_loaded_data(data, title=f"Read EEPROM {kind.upper()}")
        except Exception as exc:
            self._hardware_error(exc, title=f"Read EEPROM {kind.upper()}")

    def _write_hardware(self, kind: str) -> None:
        if not self._eeprom_unlocked:
            return
        if not self._current_data:
            self._warn(
                "No EDID or DisplayID is loaded. Pick a library entry and Load selection, use Load from file, read from hardware above, or File → Load.",
                title="Write EEPROM",
            )
            return
        display = self._selected_hardware_display()
        if display is None:
            return
        if kind == "edid" and not self._current_data.is_edid:
            self._warn("Current data is not EDID.", title="Write EEPROM EDID")
            return
        if kind == "displayid" and not self._current_data.is_displayid:
            self._warn("Current data is not DisplayID.", title="Write EEPROM DisplayID")
            return
        if not self._confirm(f"Write {kind.upper()} directly to display EEPROM?", title=f"Write EEPROM {kind.upper()}"):
            return
        try:
            self._auto_repair_current_data()
            if kind == "displayid":
                display.write_and_verify_displayid(self._current_data)
            else:
                display.write_and_verify_edid(self._current_data)
            self.status.showMessage(f"Wrote and verified {kind.upper()} on {display.label()}")
        except Exception as exc:
            self._hardware_error(exc, title=f"Write EEPROM {kind.upper()}")

    def _reset_selected(self) -> None:
        if self._windows_display is None:
            return
        if not self._windows_display.is_admin():
            self._warn("Administrator privileges are required. Start the app with run_edid_app.bat to launch elevated.", title="Reset Selected")
            return
        display = self._maintenance_selected_display() or self._selected_display()
        if display is None or not self._confirm("Reset selected display override?", title="Reset Selected"):
            return
        try:
            self._windows_display.reset_display(display.key)
            self._refresh_displays(display.key)
        except Exception as exc:
            self._error(exc, title="Reset Selected")

    def _maintenance_selected_display(self) -> object | None:
        if not hasattr(self, "maintenance_display_combo"):
            return None
        key = self.maintenance_display_combo.currentData()
        for display in self._displays:
            if display.key == key:
                return display
        return None

    def _reset_all(self) -> None:
        if self._windows_display is None:
            return
        if not self._windows_display.is_admin():
            self._warn("Administrator privileges are required. Start the app with run_edid_app.bat to launch elevated.", title="Reset All")
            return
        if not self._confirm("Reset all display overrides and graphics cache?", title="Reset All"):
            return
        try:
            self.status.showMessage(f"Reset all complete: {self._windows_display.reset_all()}")
            self._refresh_displays()
        except Exception as exc:
            self._error(exc, title="Reset All")

    def _restart_driver(self) -> None:
        self._restart_driver_with(lambda: self._windows_display.restart_display_driver(), "Restart Driver")

    def _recovery_restart_driver(self) -> None:
        self._restart_driver_with(lambda: self._windows_display.restart_display_driver_recovery(), "Recovery Restart")

    def _restart_driver_with(self, operation: Callable[[], object], title: str) -> None:
        if self._windows_display is None:
            return
        if not self._windows_display.is_admin():
            self._warn("Administrator privileges are required. Start the app with run_edid_app.bat to launch elevated.", title=title)
            return
        if not self._confirm("Restart display driver now?", title=title):
            return
        try:
            self.status.showMessage(f"{title} complete: {operation()}")
            self._refresh_displays()
        except Exception as exc:
            self._error(exc, title=title)

    def _update_data_buttons(self) -> None:
        has_data = self._current_data is not None
        is_edid = bool(self._current_data and self._current_data.is_edid)
        is_displayid = bool(self._current_data and self._current_data.is_displayid)
        has_hardware = bool(self._hardware_displays) and self._eeprom_unlocked
        self.save_button.setEnabled(has_data)
        self.install_button.setEnabled(has_data and self._windows_display is not None)
        self.eeprom_load_payload_button.setEnabled(self._eeprom_unlocked)
        sel = self._selected_display()
        self.override_remove_button.setEnabled(bool(self._windows_display and sel and sel.has_override))
        self.read_hardware_edid_button.setEnabled(has_hardware)
        self.read_hardware_displayid_button.setEnabled(has_hardware)
        self.write_hardware_edid_button.setEnabled(is_edid and has_hardware)
        self.write_hardware_displayid_button.setEnabled(is_displayid and has_hardware)
        self._update_edids_buttons()

    def _update_edids_buttons(self, data: DisplayData | None = None) -> None:
        if not hasattr(self, "edids_list"):
            return
        entry = self._edids_selected_entry()
        if entry and data is None:
            data = self._edids_load_entry_data(entry)
        has_entry = entry is not None and data is not None
        is_edid = bool(data and data.is_edid)
        is_displayid = bool(data and data.is_displayid)
        for control in (
            self.edids_duplicate_button,
            self.edids_rename_button,
            self.edids_delete_button,
            self.edids_export_button,
        ):
            control.setEnabled(has_entry)

    def _confirm(self, text: str, *, title: str) -> bool:
        return show_yes_no(
            self,
            key=f"confirm_{self._dialog_key(title)}",
            title=title,
            text=text,
            default=QMessageBox.StandardButton.No,
            label=f"{title} confirmation",
        )

    def _warn(self, text: str, *, title: str) -> None:
        self._log(f"Warning: {title}", message=text)
        show_message(
            self,
            key=f"warn_{self._dialog_key(title)}",
            title=title,
            text=text,
            icon=QMessageBox.Icon.Warning,
            label=f"{title} warning",
        )

    def _error(self, exc: Exception, *, title: str) -> None:
        message = str(exc) or type(exc).__name__
        self._log(f"Error: {title}", error=message)
        show_message(
            self,
            key=f"error_{self._dialog_key(title)}",
            title=title,
            text=message,
            icon=QMessageBox.Icon.Critical,
            label=f"{title} error",
        )

    def _hardware_error(self, exc: Exception, *, title: str) -> None:
        message = str(exc) or type(exc).__name__
        try:
            from edid.hardware_display import _diagnose_error_text

            message = f"{message}\n\n{_diagnose_error_text(message)}"
        except Exception as exc:
            log_exception("Hardware error diagnostic text failed", exc)
        show_message(
            self,
            key=f"error_{self._dialog_key(title)}",
            title=title,
            text=message,
            icon=QMessageBox.Icon.Critical,
            label=f"{title} hardware error",
        )

    def _log(self, event: str, **fields: object) -> None:
        log_event(event, **fields)

    @staticmethod
    def _dialog_key(title: str) -> str:
        return "".join(char.lower() if char.isalnum() else "_" for char in title).strip("_")

class RawBlockEditorDialog:
    def __init__(self, display_data: DisplayData, parent: QWidget | None = None) -> None:
        ui = RawblockeditordialogUi()
        self.dialog = ui.root
        self.dialog.resize(720, 520)
        self._blocks = [
            bytearray(display_data.data[index : index + EDID_BLOCK_SIZE])
            for index in range(0, len(display_data.data), EDID_BLOCK_SIZE)
            if len(display_data.data[index : index + EDID_BLOCK_SIZE]) == EDID_BLOCK_SIZE
        ]
        self.display_data = display_data
        self.block_combo = ui.block_combo
        self.block_combo.currentIndexChanged.connect(self._load_selected_block)
        self.add_button = ui.add_button
        self.add_button.clicked.connect(self._add_extension)
        self.delete_button = ui.delete_button
        self.delete_button.clicked.connect(self._delete_extension)
        self.hex_editor = ui.hex_editor
        self.hex_editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        button_box = ui.buttons
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.dialog.reject)
        self._refresh_block_combo()

    def exec(self) -> int:
        return self.dialog.exec()

    def _refresh_block_combo(self) -> None:
        current = max(0, self.block_combo.currentIndex())
        self.block_combo.blockSignals(True)
        self.block_combo.clear()
        for index, block in enumerate(self._blocks):
            self.block_combo.addItem("Base EDID" if index == 0 else f"Extension {index} (0x{block[0]:02X})")
        self.block_combo.setCurrentIndex(min(current, len(self._blocks) - 1))
        self.block_combo.blockSignals(False)
        self._load_selected_block()

    def _load_selected_block(self) -> None:
        index = self.block_combo.currentIndex()
        if 0 <= index < len(self._blocks):
            self.delete_button.setEnabled(index > 0)
            self.hex_editor.setPlainText(_bytes_to_hex(bytes(self._blocks[index])))

    def _apply_current_block(self) -> bool:
        index = self.block_combo.currentIndex()
        if index < 0:
            return False
        try:
            data = _parse_hex_block(self.hex_editor.toPlainText())
            if len(data) != EDID_BLOCK_SIZE:
                raise DisplayDataError("Each EDID block must contain exactly 128 bytes.")
            block = bytearray(data)
            block[127] = (-sum(block[:127])) & 0xFF
            self._blocks[index] = block
            return True
        except Exception as exc:
            log_exception("Raw block editor apply failed", exc)
            show_message(
                self.dialog,
                key="error_raw_block_editor_apply",
                title="Raw Block Editor",
                text=str(exc),
                icon=QMessageBox.Icon.Critical,
                label="Raw Block Editor apply failure",
            )
            return False

    def _add_extension(self) -> None:
        if self._apply_current_block():
            self._blocks.append(bytearray(EDID_BLOCK_SIZE))
            self._blocks[0][126] = len(self._blocks) - 1
            self._refresh_block_combo()
            self.block_combo.setCurrentIndex(len(self._blocks) - 1)

    def _delete_extension(self) -> None:
        index = self.block_combo.currentIndex()
        if index > 0:
            del self._blocks[index]
            self._blocks[0][126] = len(self._blocks) - 1
            self._refresh_block_combo()

    def _accept(self) -> None:
        if not self._apply_current_block():
            return
        self._blocks[0][126] = len(self._blocks) - 1
        for block in self._blocks:
            block[127] = (-sum(block[:127])) & 0xFF
        self.display_data = DisplayData(b"".join(bytes(block) for block in self._blocks))
        self.dialog.accept()


def _load_app_stylesheet() -> str:
    package_dir = Path(__file__).resolve().parent
    for path in (
        package_dir.parents[1] / "xml" / "app.qss",
        package_dir / "app.qss",
        package_dir / "ui" / "app.qss",
    ):
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8").strip()
            except Exception as exc:
                log_exception("Failed loading app stylesheet", exc, path=path)
                return ""
    return ""


class EdidCreationWizard:
    """Loads ``edid_creation_wizard.xml`` as a standalone modal window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        layout_ui = EdidcreationwizardUi()
        self.dialog = layout_ui.root
        if not isinstance(self.dialog, QWizard):
            raise TypeError("edid_creation_wizard.xml root must be QWizard")
        if parent is not None:
            self.dialog.setParent(parent, Qt.WindowType.Dialog)
            self.dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.dialog.resize(680, 560)
        # Avoid Windows Aero wizard header rendering that can make title text unreadable
        # when custom stylesheets are active.
        self.dialog.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.display_data = DisplayData(bytes(128))
        self.open_advanced_editor = True
        self._wizard_open_advanced = layout_ui.wizard_open_advanced
        self.wizard_name = layout_ui.wizard_name
        self.wizard_manufacturer = layout_ui.wizard_manufacturer
        self.wizard_product = layout_ui.wizard_product
        self.wizard_serial = layout_ui.wizard_serial
        self.wizard_width_cm = layout_ui.wizard_width_cm
        self.wizard_height_cm = layout_ui.wizard_height_cm
        self.wizard_h_active = layout_ui.wizard_h_active
        self.wizard_v_active = layout_ui.wizard_v_active
        self.wizard_refresh = layout_ui.wizard_refresh
        self.wizard_timing_mode = layout_ui.wizard_timing_mode
        self.wizard_timing_mode.clear()
        for label in ("cvt_rb", "cvt", "gtf", "automatic_hdtv"):
            self.wizard_timing_mode.addItem(label)
        self.dialog.accepted.connect(self._on_modal_accepted)

    def exec(self) -> int:
        return self.dialog.exec()

    def _on_modal_accepted(self) -> None:
        if not self._build_display_data_from_fields():
            self.dialog.reject()

    def _build_display_data_from_fields(self) -> bool:
        try:
            if isinstance(self._wizard_open_advanced, QCheckBox):
                self.open_advanced_editor = self._wizard_open_advanced.isChecked()
            self.display_data = _create_basic_edid(
                name=self.wizard_name.text().strip() or "Custom Monitor",
                manufacturer=self.wizard_manufacturer.text().strip() or "CLT",
                product_code=self.wizard_product.value(),
                serial=self.wizard_serial.value(),
                width_cm=self.wizard_width_cm.value(),
                height_cm=self.wizard_height_cm.value(),
                h_active=self.wizard_h_active.value(),
                v_active=self.wizard_v_active.value(),
                refresh=self.wizard_refresh.value(),
                timing_mode=self.wizard_timing_mode.currentText(),
            )
            return True
        except Exception as exc:
            log_exception("EDID creation wizard failed", exc)
            show_message(
                self.dialog,
                key="error_create_edid_wizard",
                title="Create EDID",
                text=str(exc),
                icon=QMessageBox.Icon.Critical,
                label="Create EDID wizard failure",
            )
            return False


def _create_basic_edid(
    *,
    name: str,
    manufacturer: str,
    product_code: int,
    serial: int,
    width_cm: int,
    height_cm: int,
    h_active: int,
    v_active: int,
    refresh: int,
    timing_mode: str,
) -> DisplayData:
    from edid.resolutions import TimingMode, make_timing
    from edid.structured_edid import DetailedTiming

    params = make_timing(h_active, v_active, refresh, TimingMode(timing_mode))
    data = bytearray(128)
    data[:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    data[8:10] = _encode_wizard_manufacturer(manufacturer)
    data[10:12] = product_code.to_bytes(2, "little")
    data[12:16] = (serial & 0xFFFFFFFF).to_bytes(4, "little")
    data[16] = 1
    data[17] = 2026 - 1990
    data[18] = 1
    data[19] = 4
    data[20] = 0xA5
    data[21] = width_cm
    data[22] = height_cm
    data[23] = 120
    data[24] = 0x06
    data[25:35] = bytes([0xEE, 0x91, 0xA3, 0x54, 0x4C, 0x99, 0x26, 0x0F, 0x50, 0x54])
    data[35:38] = b"\x00\x00\x00"
    data[38:54] = b"\x01\x01" * 8
    detailed = DetailedTiming(
        pixel_clock_khz=params.pixel_clock_khz,
        h_active=params.width,
        h_blanking=params.h_blanking,
        v_active=params.height,
        v_blanking=params.v_blanking,
        h_sync_offset=params.h_front_porch,
        h_sync_width=params.h_sync_width,
        v_sync_offset=params.v_front_porch,
        v_sync_width=params.v_sync_width,
        h_size_mm=width_cm * 10,
        v_size_mm=height_cm * 10,
        h_border=0,
        v_border=0,
        interlaced=False,
        stereo=0,
        sync_type=3,
        positive_hsync=params.h_sync_positive,
        positive_vsync=params.v_sync_positive,
        raw=b"",
    )
    data[54:72] = detailed.encode()
    text = name.encode("latin1", errors="replace")[:13]
    data[72:90] = b"\x00\x00\x00\xFC\x00" + text.ljust(13, b" ")
    data[90:108] = b"\x00\x00\x00\x10\x00" + bytes(13)
    data[108:126] = b"\x00\x00\x00\x10\x00" + bytes(13)
    data[126] = 0
    data[127] = (-sum(data[:127])) & 0xFF
    return DisplayData(bytes(data))


def _encode_wizard_manufacturer(value: str) -> bytes:
    text = (value.upper() + "   ")[:3]
    values = [max(1, min(26, ord(char) - 64)) for char in text]
    packed = (values[0] << 10) | (values[1] << 5) | values[2]
    return packed.to_bytes(2, "big")


def _bytes_to_hex(data: bytes) -> str:
    return "\n".join(" ".join(f"{byte:02X}" for byte in data[index : index + 16]) for index in range(0, len(data), 16))


def _safe_file_stem(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    return text or "edid"


def _source_kind_label(value: str) -> str:
    return {
        "file": "Imported file",
        "created": "Created in app",
        "display_active": "Monitor snapshot (active chain)",
        "display_override": "Monitor snapshot (registry override)",
    }.get(value, value.replace("_", " ").title())


def _library_row_tooltip(entry: EdidLibraryEntry) -> str:
    lines = [
        f"{entry.type_name}, {entry.size} bytes",
        f"Origin: {_source_kind_label(entry.source_kind)}",
    ]
    if entry.updated_at:
        lines.append(f"Updated: {entry.updated_at}")
    if entry.source_label:
        lines.append(f"Provenance: {entry.source_label}")
    if entry.display_key:
        lines.append(f"Related display key: {entry.display_key}")
    if entry.source_path:
        lines.append(f"Imported from: {entry.source_path}")
    if entry.content_hash:
        lines.append(f"SHA-256: {entry.content_hash}")
    return "\n".join(lines)


def _recommended_next_step(entry: EdidLibraryEntry) -> str:
    if entry.source_kind == "display_active":
        return "This is a backup of what Windows currently sees. Duplicate it before editing, then install the edited copy as an override."
    if entry.source_kind == "display_override":
        return "This is an installed override backup. Keep it for rollback, or duplicate it before making changes."
    if entry.source_kind == "file":
        return "Review the decoded data, then load it into the shared working copy, export it, or install a reversible Windows override."
    return (
        "Review the decoded data and warnings. Load into the shared working copy, then install a reversible Windows override "
        "from this tab or the Windows Override tab—or use the EEPROM tab only for permanent hardware writes."
    )


def _parse_hex_block(text: str) -> bytes:
    tokens = re.findall(r"0[xX]([0-9A-Fa-f]{2})|\b([0-9A-Fa-f]{2})\b", text)
    if not tokens:
        raise DisplayDataError("No hex bytes found.")
    return bytes(int(first or second, 16) for first, second in tokens)


def run_gui() -> int:
    app = QApplication.instance() or QApplication([])
    QCoreApplication.setOrganizationName("Colorlight")
    QCoreApplication.setApplicationName("EdidTools")
    app.setStyleSheet(_load_app_stylesheet())
    window = MainWindow()
    window.show()
    return int(app.exec())
