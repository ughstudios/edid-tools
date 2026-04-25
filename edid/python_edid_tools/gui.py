from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Callable

from .edid_data import EDID_BLOCK_SIZE, DisplayData, DisplayDataError, load_display_data, save_display_data
from .logging_utils import log_event, log_exception

try:
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QAction, QFontDatabase
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QStackedWidget,
        QStatusBar,
        QStyle,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
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

        self._setup_ui()
        self._init_windows_backend()
        self._init_hardware_backend()
        self._load_cached_eeprom_login()
        self._refresh_displays()
        self._refresh_monitor_manager()
        self._refresh_hardware_displays()

    def _setup_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        tabs = QTabWidget()
        outer.addWidget(tabs, 1)

        override_tab = QWidget()
        override_layout = QVBoxLayout(override_tab)
        tabs.addTab(override_tab, "Windows Override" if os.name == "nt" else "Windows Override (unavailable)")

        manager_tab = QWidget()
        manager_layout = QVBoxLayout(manager_tab)
        tabs.addTab(manager_tab, "Monitor Manager")

        eeprom_tab = QWidget()
        eeprom_layout = QVBoxLayout(eeprom_tab)
        tabs.addTab(eeprom_tab, "Permanent EEPROM Write")

        maintenance_tab = QWidget()
        maintenance_layout = QVBoxLayout(maintenance_tab)
        tabs.addTab(maintenance_tab, "Windows Driver Maintenance" if os.name == "nt" else "Windows Driver Maintenance (unavailable)")

        self._setup_override_tab(override_layout)
        self._setup_monitor_manager_tab(manager_layout)
        self._setup_eeprom_tab(eeprom_layout)
        self._setup_maintenance_tab(maintenance_layout)
        self._setup_menu()
        self._apply_style()

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")
        self._update_eeprom_page()
        self._update_data_buttons()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QGroupBox {
                font-weight: 600;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                min-height: 28px;
                padding: 4px 10px;
            }
            QLabel#hintLabel {
                color: #b8b8b8;
            }
            """
        )

    def _icon(self, icon: QStyle.StandardPixmap):
        return self.style().standardIcon(icon)

    def _action_button(self, text: str, icon: QStyle.StandardPixmap, tooltip: str | None = None) -> QPushButton:
        button = QPushButton(text)
        button.setIcon(self._icon(icon))
        button.setIconSize(QSize(18, 18))
        if tooltip:
            button.setToolTip(tooltip)
        return button

    def _setup_override_tab(self, layout: QVBoxLayout) -> None:
        intro = QLabel(
            (
                "Recommended for most Windows users: edit or load EDID data, then install a reversible Windows override. "
                "This does not permanently write the monitor EEPROM."
                if os.name == "nt"
                else "Windows EDID overrides are only available on Windows. You can still load, decode, edit, and save EDID files here."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        toolbar = QHBoxLayout()
        layout.addLayout(toolbar)
        toolbar.addWidget(QLabel("Step 1 - Choose display:"))
        self.display_combo = QComboBox()
        self.display_combo.currentIndexChanged.connect(self._on_display_changed)
        toolbar.addWidget(self.display_combo, 1)
        self.refresh_button = self._action_button("Refresh displays", QStyle.SP_BrowserReload, "Reload the monitor list from Windows.")
        self.refresh_button.clicked.connect(self._refresh_displays)
        toolbar.addWidget(self.refresh_button)

        data_group = QGroupBox("Step 2 - Load, decode, or edit EDID data")
        layout.addWidget(data_group, 1)
        grid = QGridLayout(data_group)
        source_label = QLabel("Choose a source")
        source_label.setObjectName("hintLabel")
        grid.addWidget(source_label, 0, 0, 1, 3)
        self.read_active_button = self._action_button(
            "Read EDID from selected display",
            QStyle.SP_ComputerIcon,
            "Loads the EDID Windows currently sees for the selected display.",
        )
        self.read_active_button.clicked.connect(lambda: self._read_registry_edid("active"))
        grid.addWidget(self.read_active_button, 1, 0)
        self.read_override_button = self._action_button(
            "Read installed override",
            QStyle.SP_DriveHDIcon,
            "Loads the EDID override currently installed in Windows, if one exists.",
        )
        self.read_override_button.clicked.connect(lambda: self._read_registry_edid("override"))
        grid.addWidget(self.read_override_button, 1, 1)
        self.save_button = self._action_button("Save EDID to file...", QStyle.SP_DialogSaveButton, "Save the current working EDID/DisplayID to a file.")
        self.save_button.clicked.connect(self._save_file)
        grid.addWidget(self.save_button, 1, 2)

        preview_layout = QHBoxLayout()
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)
        self.text_box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.text_box.setPlaceholderText("Raw EDID hex will appear here.")
        preview_layout.addWidget(self.text_box, 1)
        self.decoded_preview_box = QTextEdit()
        self.decoded_preview_box.setReadOnly(True)
        self.decoded_preview_box.setPlaceholderText("Decoded EDID details will appear here.")
        preview_layout.addWidget(self.decoded_preview_box, 1)
        grid.addLayout(preview_layout, 2, 0, 1, 3)
        self.current_data_label = QLabel("No EDID loaded yet. Start by reading from a display or loading an EDID file.")
        self.current_data_label.setWordWrap(True)
        grid.addWidget(self.current_data_label, 3, 0, 1, 3)

        edit_label = QLabel("Load or save")
        edit_label.setObjectName("hintLabel")
        grid.addWidget(edit_label, 4, 0, 1, 3)
        self.load_button = self._action_button("Load EDID file...", QStyle.SP_DialogOpenButton, "Load EDID/DisplayID data from BIN, DAT, TXT, or INF.")
        self.load_button.clicked.connect(self._load_file)
        grid.addWidget(self.load_button, 5, 0)

        apply_group = QGroupBox("Step 3 - Apply safely")
        layout.addWidget(apply_group)
        apply_layout = QHBoxLayout(apply_group)
        apply_hint = QLabel("Installs a reversible Windows registry override.")
        apply_hint.setWordWrap(True)
        apply_layout.addWidget(apply_hint, 1)
        self.install_button = self._action_button(
            "Install Windows EDID override",
            QStyle.SP_DialogApplyButton,
            "Writes a Windows registry override. This is reversible and safer than EEPROM writing.",
        )
        self.install_button.clicked.connect(self._install_override)
        apply_layout.addWidget(self.install_button)

    def _setup_monitor_manager_tab(self, layout: QVBoxLayout) -> None:
        intro = QLabel(
            "Monitor editor: this shows the selected monitor's EDID broken into sections. "
            "Changes here only update the working EDID until you install it as an override."
            if os.name == "nt"
            else "Monitor management through Windows registry is only available on Windows."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        toolbar = QHBoxLayout()
        layout.addLayout(toolbar)
        toolbar.addWidget(QLabel("Monitor:"))
        self.manager_selected_combo = QComboBox()
        self.manager_selected_combo.currentIndexChanged.connect(self._refresh_manager_edid_lists)
        toolbar.addWidget(self.manager_selected_combo, 1)
        self.manager_edit_button = self._action_button("Edit...", QStyle.SP_FileDialogContentsView, "Open advanced editors for the selected monitor's working EDID.")
        self.manager_edit_button.clicked.connect(self._manager_edit_selected)
        toolbar.addWidget(self.manager_edit_button)
        self.manager_copy_button = self._action_button("Copy", QStyle.SP_FileDialogDetailedView, "Copy the selected monitor's working EDID.")
        self.manager_copy_button.clicked.connect(self._manager_copy_selected)
        toolbar.addWidget(self.manager_copy_button)
        self.manager_paste_button = self._action_button("Paste", QStyle.SP_DialogApplyButton, "Install the copied EDID as an override for the selected monitor.")
        self.manager_paste_button.clicked.connect(self._manager_paste_to_selected)
        toolbar.addWidget(self.manager_paste_button)
        self.manager_delete_button = self._action_button("Delete override", QStyle.SP_TrashIcon, "Remove only the EDID override for the selected monitor.")
        self.manager_delete_button.clicked.connect(self._manager_remove_selected_override)
        toolbar.addWidget(self.manager_delete_button)
        self.manager_delete_monitor_button = self._action_button("Delete monitor data", QStyle.SP_MessageBoxWarning)
        self.manager_delete_monitor_button.setToolTip("Matches the native delete behavior: removes EDID, EDID_OVERRIDE, and EDID_RECOVERY data for this monitor.")
        self.manager_delete_monitor_button.clicked.connect(self._manager_delete_selected_monitor_data)
        toolbar.addWidget(self.manager_delete_monitor_button)
        self.manager_refresh_button = self._action_button("Refresh monitor list", QStyle.SP_BrowserReload, "Reload monitor entries and EDID data from Windows.")
        self.manager_refresh_button.clicked.connect(self._refresh_monitor_manager)
        toolbar.addWidget(self.manager_refresh_button)

        body = QHBoxLayout()
        layout.addLayout(body, 1)

        established_group = QGroupBox("Established resolutions")
        body.addWidget(established_group)
        established_layout = QVBoxLayout(established_group)
        established_help = QLabel("Old compatibility modes advertised by the monitor. Usually safe to leave alone.")
        established_help.setObjectName("hintLabel")
        established_help.setWordWrap(True)
        established_layout.addWidget(established_help)
        self.manager_established_checks: list[QCheckBox] = []
        from .resolutions import ESTABLISHED_TIMINGS

        for name, _byte, _bit in ESTABLISHED_TIMINGS:
            check = QCheckBox(name)
            check.setEnabled(False)
            self.manager_established_checks.append(check)
            established_layout.addWidget(check)
        established_layout.addStretch(1)

        lists_layout = QVBoxLayout()
        body.addLayout(lists_layout, 1)

        self.manager_summary_label = QLabel("Select a monitor to see what its EDID advertises.")
        self.manager_summary_label.setWordWrap(True)
        self.manager_summary_label.setObjectName("hintLabel")
        lists_layout.addWidget(self.manager_summary_label)

        self.manager_detailed_list = self._manager_section(
            lists_layout,
            "Detailed resolutions",
            "Exact video modes. The first one is usually the preferred/native mode.",
            self._manager_add_detailed,
            self._manager_edit_selected,
            self._manager_delete_detailed,
            self._manager_delete_all_detailed,
        )
        self.manager_standard_list = self._manager_section(
            lists_layout,
            "Standard resolutions",
            "Older compact resolution entries. Modern displays often have none.",
            self._manager_add_standard,
            self._manager_edit_selected,
            self._manager_delete_standard,
            self._manager_delete_all_standard,
        )
        self.manager_extension_list = self._manager_section(
            lists_layout,
            "Extension blocks",
            "Extra EDID blocks for HDMI/DisplayID/HDR/audio/VRR and other capabilities.",
            self._manager_add_extension,
            self._manager_edit_selected,
            self._manager_delete_extension,
            self._manager_delete_all_extensions,
        )

    def _manager_section(
        self,
        parent: QVBoxLayout,
        title: str,
        help_text: str,
        add_callback: Callable[[], None],
        edit_callback: Callable[[], None],
        delete_callback: Callable[[], None],
        delete_all_callback: Callable[[], None],
    ) -> QListWidget:
        group = QGroupBox(title)
        parent.addWidget(group)
        layout = QVBoxLayout(group)
        help_label = QLabel(help_text)
        help_label.setObjectName("hintLabel")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        items = QListWidget()
        layout.addWidget(items)
        buttons = QHBoxLayout()
        for text, slot in (
            ("Add...", add_callback),
            ("Edit...", edit_callback),
            ("Delete", delete_callback),
            ("Delete all", delete_all_callback),
        ):
            icon = {
                "Add...": QStyle.SP_FileDialogNewFolder,
                "Edit...": QStyle.SP_FileDialogContentsView,
                "Delete": QStyle.SP_TrashIcon,
                "Delete all": QStyle.SP_DialogResetButton,
            }.get(text, QStyle.SP_FileIcon)
            tip = {
                "Add...": f"Add an item to {title}.",
                "Edit...": f"Edit the selected item in {title}.",
                "Delete": f"Delete the selected item from {title}.",
                "Delete all": f"Delete every item in {title}.",
            }.get(text)
            button = self._action_button(text, icon, tip)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return items

    def _setup_maintenance_tab(self, layout: QVBoxLayout) -> None:
        intro = QLabel(
            (
                "These actions affect Windows display-driver state and cached display configuration. "
                "Use them after installing or removing overrides, or if Windows needs to redetect displays."
                if os.name == "nt"
                else "Windows driver maintenance actions are not available on this operating system."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        ops_group = QGroupBox("Windows display-driver tools")
        layout.addWidget(ops_group)
        ops_layout = QVBoxLayout(ops_group)
        selector = QHBoxLayout()
        selector.addWidget(QLabel("Selected display:"))
        self.maintenance_display_combo = QComboBox()
        selector.addWidget(self.maintenance_display_combo, 1)
        ops_layout.addLayout(selector)
        ops = QHBoxLayout()
        ops_layout.addLayout(ops)
        self.reset_selected_button = self._action_button(
            "Remove selected override",
            QStyle.SP_DialogResetButton,
            "Removes the EDID override for the selected display from Windows.",
        )
        self.reset_selected_button.clicked.connect(self._reset_selected)
        ops.addWidget(self.reset_selected_button)
        self.reset_all_button = self._action_button(
            "Reset all overrides",
            QStyle.SP_TrashIcon,
            "Clears all display overrides and display-driver cache entries.",
        )
        self.reset_all_button.clicked.connect(self._reset_all)
        ops.addWidget(self.reset_all_button)
        self.restart_button = self._action_button(
            "Restart display driver",
            QStyle.SP_BrowserReload,
            "Disables and re-enables display adapters so Windows redetects displays.",
        )
        self.restart_button.clicked.connect(self._restart_driver)
        ops.addWidget(self.restart_button)
        self.recovery_restart_button = self._action_button(
            "Recovery restart",
            QStyle.SP_MessageBoxWarning,
            "Temporarily stages override recovery data, restarts the driver, then restores overrides.",
        )
        self.recovery_restart_button.clicked.connect(self._recovery_restart_driver)
        ops.addWidget(self.recovery_restart_button)
        layout.addStretch(1)

    def _setup_eeprom_tab(self, layout: QVBoxLayout) -> None:
        warning = QLabel(
            "Advanced only: EEPROM writes are permanent hardware writes. Hardware access depends on the operating system and GPU/backend. "
            "On Windows this app uses AMD ADL/NVIDIA NVAPI; on Linux it can use ddcutil for EDID reads if available."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self.eeprom_stack = QStackedWidget()
        layout.addWidget(self.eeprom_stack, 1)

        login_page = QWidget()
        login_layout = QVBoxLayout(login_page)
        login_text = QLabel("Sign in with an approved project-tracker account to unlock permanent EEPROM read/write operations.")
        login_text.setWordWrap(True)
        login_layout.addWidget(login_text)
        tracker_link = QLabel('<a href="https://tracker.colorlightcloud.com">Open project tracker</a>')
        tracker_link.setOpenExternalLinks(True)
        login_layout.addWidget(tracker_link)
        form = QFormLayout()
        self.eeprom_email_edit = QLineEdit()
        self.eeprom_email_edit.setPlaceholderText("email@example.com")
        self.eeprom_password_edit = QLineEdit()
        self.eeprom_password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Email", self.eeprom_email_edit)
        form.addRow("Password", self.eeprom_password_edit)
        login_layout.addLayout(form)
        self.eeprom_login_button = self._action_button("Sign In", QStyle.SP_DialogApplyButton, "Authenticate with project-tracker to unlock EEPROM operations.")
        self.eeprom_login_button.clicked.connect(self._unlock_eeprom_writer)
        login_layout.addWidget(self.eeprom_login_button)
        self.eeprom_login_status = QLabel("")
        login_layout.addWidget(self.eeprom_login_status)
        login_layout.addStretch(1)
        self.eeprom_stack.addWidget(login_page)

        controls_page = QWidget()
        controls_layout = QVBoxLayout(controls_page)
        self.eeprom_stack.addWidget(controls_page)
        hardware_bar = QHBoxLayout()
        controls_layout.addLayout(hardware_bar)
        hardware_bar.addWidget(QLabel("Step 1 - Choose hardware output:"))
        self.hardware_combo = QComboBox()
        hardware_bar.addWidget(self.hardware_combo, 1)
        self.refresh_hardware_button = self._action_button("Refresh hardware outputs", QStyle.SP_BrowserReload, "Rescan GPU/DDC hardware outputs.")
        self.refresh_hardware_button.clicked.connect(self._refresh_hardware_displays)
        hardware_bar.addWidget(self.refresh_hardware_button)

        hardware_group = QGroupBox("Step 2 - Read or write monitor EEPROM")
        controls_layout.addWidget(hardware_group)
        hardware_grid = QGridLayout(hardware_group)
        self.eeprom_auth_label = QLabel("Unlocked.")
        hardware_grid.addWidget(self.eeprom_auth_label, 0, 0, 1, 2)
        self.logout_eeprom_button = self._action_button("Sign Out", QStyle.SP_DialogCloseButton, "Clear cached project-tracker login and lock EEPROM operations.")
        self.logout_eeprom_button.clicked.connect(self._logout_eeprom_writer)
        hardware_grid.addWidget(self.logout_eeprom_button, 1, 0, 1, 2)
        hardware_grid.addWidget(
            QLabel("Tip: read from hardware first to make a backup. To write new data, load or edit EDID data in the Windows Override tab, then return here."),
            2,
            0,
            1,
            2,
        )
        self.read_hardware_edid_button = self._action_button("Backup: read EDID from EEPROM", QStyle.SP_DialogSaveButton, "Read EDID bytes from the selected hardware output.")
        self.read_hardware_edid_button.clicked.connect(lambda: self._read_hardware("edid"))
        hardware_grid.addWidget(self.read_hardware_edid_button, 3, 0)
        self.read_hardware_displayid_button = self._action_button("Backup: read DisplayID from EEPROM", QStyle.SP_DialogSaveButton, "Read DisplayID bytes from the selected hardware output.")
        self.read_hardware_displayid_button.clicked.connect(lambda: self._read_hardware("displayid"))
        hardware_grid.addWidget(self.read_hardware_displayid_button, 3, 1)
        self.write_hardware_edid_button = self._action_button("Permanent write: EDID to EEPROM", QStyle.SP_MessageBoxWarning, "Permanently write current EDID to the selected display EEPROM.")
        self.write_hardware_edid_button.clicked.connect(lambda: self._write_hardware("edid"))
        hardware_grid.addWidget(self.write_hardware_edid_button, 4, 0)
        self.write_hardware_displayid_button = self._action_button("Permanent write: DisplayID to EEPROM", QStyle.SP_MessageBoxWarning, "Permanently write current DisplayID to the selected display EEPROM.")
        self.write_hardware_displayid_button.clicked.connect(lambda: self._write_hardware("displayid"))
        hardware_grid.addWidget(self.write_hardware_displayid_button, 4, 1)
        self.hardware_backend_label = QLabel("")
        self.hardware_backend_label.setWordWrap(True)
        hardware_grid.addWidget(self.hardware_backend_label, 5, 0, 1, 2)
        controls_layout.addStretch(1)
        self._set_hardware_controls_enabled(False)

    def _setup_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        load_action = QAction("Load...", self)
        load_action.triggered.connect(self._load_file)
        file_menu.addAction(load_action)
        save_action = QAction("Save...", self)
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)

        tools_menu = self.menuBar().addMenu("Tools")
        wizard_action = QAction("EDID Creation Wizard...", self)
        wizard_action.triggered.connect(self._open_edid_wizard)
        tools_menu.addAction(wizard_action)

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _init_windows_backend(self) -> None:
        try:
            from . import windows_display

            self._windows_display = windows_display
        except Exception as exc:
            log_exception("Windows backend initialization failed", exc)
            self._windows_display = None
            self._set_windows_controls_enabled(False)
            self._warn(str(exc), title="Windows Backend Unavailable")

    def _init_hardware_backend(self) -> None:
        try:
            from . import hardware_display

            self._hardware_display = hardware_display
        except Exception as exc:
            log_exception("Hardware backend initialization failed", exc)
            self._hardware_display = None
            self._set_hardware_controls_enabled(False)
            self._warn(str(exc), title="Hardware Backend Unavailable")

    def _load_cached_eeprom_login(self) -> None:
        try:
            from .issue_tracker_auth import load_cached_auth

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
            self.reset_selected_button,
            self.reset_all_button,
            self.restart_button,
            self.recovery_restart_button,
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

    def _refresh_displays(self, preferred_key: str | None = None) -> None:
        if self._windows_display is None:
            return
        preferred_key = preferred_key or self._current_display_key()
        try:
            self._displays = self._windows_display.list_display_instances()
        except Exception as exc:
            self._displays = []
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
            for list_widget in (self.manager_detailed_list, self.manager_standard_list, self.manager_extension_list):
                list_widget.clear()
            return
        try:
            self._displays = self._windows_display.list_display_instances()
        except Exception as exc:
            self._error(exc, title="Monitor Manager")
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
        if not hasattr(self, "manager_detailed_list"):
            return
        for list_widget in (self.manager_detailed_list, self.manager_standard_list, self.manager_extension_list):
            list_widget.clear()
        for check in self.manager_established_checks:
            check.setChecked(False)
        data = self._manager_current_edid_data()
        if not data or not data.is_edid:
            self.manager_summary_label.setText("No editable EDID data is available for this monitor.")
            return
        try:
            from .resolutions import EstablishedTimingSet
            from .structured_edid import StructuredEDID

            structured = StructuredEDID.parse(data)
        except Exception as exc:
            log_exception("Monitor EDID section refresh failed", exc, key=self._manager_current_key())
            return
        self._log(
            "Refreshing monitor EDID sections",
            key=self._manager_current_key(),
            working=self._manager_current_key() in self._manager_working_edids if self._manager_current_key() else False,
            detailed=len(structured.detailed_timings),
            standard=sum(1 for timing in structured.standard_timings if timing.is_used),
            extensions=len(structured.extensions),
        )
        source = "working copy" if (self._manager_current_key() in self._manager_working_edids if self._manager_current_key() else False) else "monitor data"
        self.manager_summary_label.setText(
            f"Showing {source}: {len(structured.detailed_timings)} detailed, "
            f"{sum(1 for timing in structured.standard_timings if timing.is_used)} standard, "
            f"{len(structured.extensions)} extension block(s)."
        )
        established = EstablishedTimingSet(structured.established_timings)
        for check in self.manager_established_checks:
            check.setChecked(established.is_enabled(check.text()))
        for timing in structured.detailed_timings:
            refresh = timing.refresh_rate
            refresh_text = "unknown" if refresh is None else f"{refresh:.2f} Hz"
            self.manager_detailed_list.addItem(
                f"{timing.h_active}x{timing.v_active} @ {refresh_text} ({timing.pixel_clock_khz / 1000:.3f} MHz)"
            )
        if self.manager_detailed_list.count() == 0:
            self.manager_detailed_list.addItem("No detailed resolutions")
        for timing in structured.standard_timings:
            if timing.is_used:
                self.manager_standard_list.addItem(f"{timing.width}x{timing.height} @ {timing.refresh_rate} Hz")
        if self.manager_standard_list.count() == 0:
            self.manager_standard_list.addItem("No standard resolutions")
        for extension in structured.extensions:
            self.manager_extension_list.addItem(
                f"{extension.type_name}: {len(extension.data_blocks)} data blocks, {len(extension.detailed_timings)} detailed timings"
            )
        if self.manager_extension_list.count() == 0:
            self.manager_extension_list.addItem("No extension blocks")

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
            from .issue_tracker_auth import authenticate_issue_tracker_user, save_cached_auth

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
            from .issue_tracker_auth import clear_cached_auth

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
            self._process_loaded_data(load_display_data(file_name, trim=False), title="Load File")
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
            self._warn(f"Selected monitor has no {source} EDID.", title="Monitor Manager")
            return
        self._manager_working_edids[display.key] = data.clone()
        self._process_loaded_data(data, title=f"Load {source.capitalize()} EDID")
        self._refresh_manager_edid_lists()

    def _manager_edit_selected(self) -> None:
        data = self._manager_current_edid_data()
        if not data:
            self._warn("Selected monitor has no EDID data to edit.", title="Monitor Manager")
            return
        self._process_loaded_data(data, title="Edit Monitor EDID")
        self._open_typed_editors()
        self._refresh_manager_edid_lists()

    def _manager_copy_selected(self) -> None:
        data = self._manager_current_edid_data()
        if not data:
            self._warn("Selected monitor has no EDID data to copy.", title="Monitor Manager")
            return
        self._manager_clipboard = data.clone()
        self.status.showMessage("Monitor EDID copied. Choose another monitor and use Paste to install it as an override.")

    def _manager_paste_to_selected(self) -> None:
        if self._windows_display is None or not self._manager_clipboard:
            return
        display = self._manager_selected_display()
        if not display:
            return
        if not self._confirm(f"Install copied EDID as an override for {display.name}?", title="Monitor Manager"):
            return
        try:
            self._windows_display.install_edid_override(self._manager_clipboard, target=display.key, allow_invalid=True)
            self._manager_working_edids.pop(display.key, None)
            self._refresh_displays(display.key)
            self._refresh_monitor_manager(display.key)
            self.status.showMessage("Copied EDID installed as override.")
        except Exception as exc:
            self._error(exc, title="Monitor Manager")

    def _manager_working_structured(self):
        data = self._manager_current_edid_data()
        if not data:
            return None
        try:
            from .structured_edid import StructuredEDID

            return StructuredEDID.parse(data)
        except Exception as exc:
            self._error(exc, title="Monitor Manager")
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
            self._error(exc, title="Monitor Manager")

    def _manager_add_detailed(self) -> None:
        structured = self._manager_working_structured()
        if not structured:
            return
        self._process_loaded_data(structured.encode(), title="Add Detailed Resolution")
        self._open_typed_editors()

    def _manager_delete_detailed(self) -> None:
        structured = self._manager_working_structured()
        row = self.manager_detailed_list.currentRow()
        if structured and 0 <= row < len(structured.detailed_timings):
            del structured.detailed_timings[row]
            self._manager_apply_structured(structured, "Detailed resolution deleted.")

    def _manager_delete_all_detailed(self) -> None:
        structured = self._manager_working_structured()
        if structured:
            structured.detailed_timings.clear()
            self._manager_apply_structured(structured, "All detailed resolutions deleted.")

    def _manager_add_standard(self) -> None:
        structured = self._manager_working_structured()
        if not structured:
            return
        for index, timing in enumerate(structured.standard_timings):
            if not timing.is_used:
                timing.width = 1920
                timing.height = 1080
                timing.refresh_rate = 60
                timing.aspect = (16, 9)
                timing.raw = timing.encode()
                self._log("Standard resolution added", width=1920, height=1080, refresh=60, slot=index)
                self._manager_apply_structured(structured, "Added standard resolution 1920x1080 @ 60 Hz.")
                return
        self._warn("No free standard resolution slots are available.", title="Monitor Manager")

    def _manager_delete_standard(self) -> None:
        structured = self._manager_working_structured()
        row = self.manager_standard_list.currentRow()
        used_indexes = [index for index, timing in enumerate(structured.standard_timings) if timing.is_used] if structured else []
        if structured and 0 <= row < len(used_indexes):
            structured.standard_timings[used_indexes[row]] = structured.standard_timings[used_indexes[row]].unused(used_indexes[row])
            self._manager_apply_structured(structured, "Standard resolution deleted.")

    def _manager_delete_all_standard(self) -> None:
        structured = self._manager_working_structured()
        if structured:
            structured.standard_timings = [timing.unused(index) for index, timing in enumerate(structured.standard_timings)]
            self._manager_apply_structured(structured, "All standard resolutions deleted.")

    def _manager_add_extension(self) -> None:
        structured = self._manager_working_structured()
        if not structured:
            return
        from .structured_edid import ExtensionBlock

        structured.add_extension(ExtensionBlock(index=len(structured.extensions) + 1, tag=0x02, revision=3, dtd_offset=4, flags=0))
        self._manager_apply_structured(structured, "CEA extension added.")

    def _manager_delete_extension(self) -> None:
        structured = self._manager_working_structured()
        row = self.manager_extension_list.currentRow()
        if structured and 0 <= row < len(structured.extensions):
            structured.delete_extension(row)
            self._manager_apply_structured(structured, "Extension deleted.")

    def _manager_delete_all_extensions(self) -> None:
        structured = self._manager_working_structured()
        if structured:
            structured.extensions.clear()
            self._manager_apply_structured(structured, "All extensions deleted.")

    def _manager_export_selected(self, source: str) -> None:
        display = self._manager_selected_display()
        if not display:
            return
        data = display.override_data if source == "override" else display.active_data
        if data is None:
            self._warn(f"Selected monitor has no {source} EDID.", title="Monitor Manager")
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
            self._warn("Selected monitor has no override to remove.", title="Monitor Manager")
            return
        if not self._confirm(f"Remove EDID override for {display.name}?", title="Monitor Manager"):
            return
        try:
            self._windows_display.reset_display(display.key)
            self._manager_working_edids.pop(display.key, None)
            self._refresh_displays(display.key)
            self._refresh_monitor_manager(display.key)
            self.status.showMessage("Override removed.")
        except Exception as exc:
            self._error(exc, title="Monitor Manager")

    def _manager_delete_selected_monitor_data(self) -> None:
        if self._windows_display is None:
            return
        display = self._manager_selected_display()
        if not display:
            return
        self._log(
            "Delete monitor data requested",
            key=display.key,
            device_id=display.device_id,
            instance_id=display.instance_id,
            admin=self._windows_display.is_admin(),
        )
        message = (
            f"Delete EDID data for {display.name}?\n\n"
            f"{display.key}\n\n"
            "This removes EDID, EDID_OVERRIDE, and EDID_RECOVERY values for this monitor. "
            "It does not delete the protected Plug and Play device instance key."
        )
        if not self._confirm(message, title="Delete Monitor Data"):
            self._log("Delete monitor data cancelled", key=display.key)
            return
        try:
            self._windows_display.reset_display(display.key)
            self._log("Delete monitor data succeeded", key=display.key)
            self._manager_working_edids.pop(display.key, None)
            self._refresh_displays(display.key)
            self._refresh_monitor_manager(display.key)
            self.status.showMessage("Monitor EDID data deleted.")
        except Exception as exc:
            self._log("Delete monitor data failed", key=display.key, error=exc)
            self._error(exc, title="Delete Monitor Data")

    def _process_loaded_data(self, data: DisplayData, *, title: str) -> None:
        selected = self._selected_display()
        incoming_id = data.product_id()
        selected_id = selected.product_id if selected else None
        if incoming_id and selected_id and len(incoming_id) == len(selected_id) and incoming_id != selected_id:
            if not self._confirm(f"Product ID does not match selected display ({incoming_id} vs {selected_id}). Load anyway?", title=title):
                return
        self._current_data = data
        self._refresh_textbox()
        warnings = data.warnings()
        if warnings:
            self._warn("\n".join(warnings), title=title)

    def _refresh_textbox(self) -> None:
        self.text_box.setPlainText("No data" if not self._current_data else self._current_data.to_text())
        if not self._current_data:
            self.current_data_label.setText("No EDID loaded yet. Start by reading from a display or loading an EDID file.")
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
        self._update_data_buttons()

    def _decoded_preview_text(self) -> str:
        if not self._current_data:
            return ""
        try:
            from .edid_decode_text import decode_display_data

            return decode_display_data(self._current_data, include_hex=False)
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
        QMessageBox.information(
            self,
            "About Colorlight EDID/DisplayID Tools",
            "Colorlight EDID/DisplayID Tools\n\n"
            "Display override editor and EEPROM writer.\n\n"
            "Contact: daniel.gleason@lednets.com",
        )

    def _open_edid_wizard(self) -> None:
        dialog = EdidCreationWizard(self)
        if dialog.exec() == QDialog.Accepted:
            self._current_data = dialog.display_data
            self._refresh_textbox()
            self.status.showMessage("Created a new EDID. Review it, then save or install it as an override.")

    def _open_typed_editors(self) -> None:
        if not self._current_data:
            return
        try:
            from .gui_editors import TypedEditorDialog

            dialog = TypedEditorDialog(self._current_data, self)
            if dialog.exec() == QDialog.Accepted:
                self._current_data = dialog.display_data
                self._refresh_textbox()
        except Exception as exc:
            self._error(exc, title="Typed Editors")

    def _open_block_editor(self) -> None:
        if not self._current_data or not self._current_data.is_edid:
            return
        dialog = RawBlockEditorDialog(self._current_data, self)
        if dialog.exec() == QDialog.Accepted:
            self._current_data = dialog.display_data
            self._refresh_textbox()

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
        if not self._eeprom_unlocked or not self._current_data:
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
        self.read_hardware_edid_button.setEnabled(has_hardware)
        self.read_hardware_displayid_button.setEnabled(has_hardware)
        self.write_hardware_edid_button.setEnabled(is_edid and has_hardware)
        self.write_hardware_displayid_button.setEnabled(is_displayid and has_hardware)

    def _confirm(self, text: str, *, title: str) -> bool:
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def _warn(self, text: str, *, title: str) -> None:
        self._log(f"Warning: {title}", message=text)
        QMessageBox.warning(self, title, text)

    def _error(self, exc: Exception, *, title: str) -> None:
        message = str(exc) or type(exc).__name__
        self._log(f"Error: {title}", error=message)
        QMessageBox.critical(self, title, message)

    def _hardware_error(self, exc: Exception, *, title: str) -> None:
        message = str(exc) or type(exc).__name__
        try:
            from .hardware_display import _diagnose_error_text

            message = f"{message}\n\n{_diagnose_error_text(message)}"
        except Exception as exc:
            log_exception("Hardware error diagnostic text failed", exc)
        QMessageBox.critical(self, title, message)

    def _log(self, event: str, **fields: object) -> None:
        log_event(event, **fields)

class RawBlockEditorDialog(QDialog):
    def __init__(self, display_data: DisplayData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Raw EDID Block Editor")
        self.resize(720, 520)
        self._blocks = [
            bytearray(display_data.data[index : index + EDID_BLOCK_SIZE])
            for index in range(0, len(display_data.data), EDID_BLOCK_SIZE)
            if len(display_data.data[index : index + EDID_BLOCK_SIZE]) == EDID_BLOCK_SIZE
        ]
        self.display_data = display_data
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        layout.addLayout(top)
        top.addWidget(QLabel("Block:"))
        self.block_combo = QComboBox()
        self.block_combo.currentIndexChanged.connect(self._load_selected_block)
        top.addWidget(self.block_combo, 1)
        self.add_button = QPushButton("Add Extension")
        self.add_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        self.add_button.setToolTip("Append a new blank 128-byte EDID extension block.")
        self.add_button.clicked.connect(self._add_extension)
        top.addWidget(self.add_button)
        self.delete_button = QPushButton("Delete Extension")
        self.delete_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.delete_button.setToolTip("Delete the selected EDID extension block.")
        self.delete_button.clicked.connect(self._delete_extension)
        top.addWidget(self.delete_button)
        self.hex_editor = QTextEdit()
        self.hex_editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        layout.addWidget(self.hex_editor, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_block_combo()

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
            QMessageBox.critical(self, "Raw Block Editor", str(exc))
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
        self.accept()


class EdidCreationWizard(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EDID Creation Wizard")
        self.resize(680, 560)
        self.display_data = DisplayData(bytes(128))
        layout = QVBoxLayout(self)

        intro = QLabel(
            "This wizard creates a simple, valid base EDID for Windows overrides. "
            "Use it when you need a clean starting point. Advanced HDMI/HDR/audio data can be added later in Monitor Manager."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        basics = QWidget()
        basics_form = QFormLayout(basics)
        self.wizard_name = QLineEdit("Custom Monitor")
        self.wizard_manufacturer = QLineEdit("CLT")
        self.wizard_product = QSpinBox()
        self.wizard_product.setRange(0, 0xFFFF)
        self.wizard_product.setValue(0x1234)
        self.wizard_serial = QSpinBox()
        self.wizard_serial.setRange(0, 999999999)
        self.wizard_serial.setValue(1)
        self.wizard_width_cm = QSpinBox()
        self.wizard_width_cm.setRange(1, 255)
        self.wizard_width_cm.setValue(60)
        self.wizard_height_cm = QSpinBox()
        self.wizard_height_cm.setRange(1, 255)
        self.wizard_height_cm.setValue(34)
        basics_form.addRow("Display name", self.wizard_name)
        basics_form.addRow("Manufacturer ID (3 letters)", self.wizard_manufacturer)
        basics_form.addRow("Product code", self.wizard_product)
        basics_form.addRow("Serial number", self.wizard_serial)
        basics_form.addRow("Physical width (cm)", self.wizard_width_cm)
        basics_form.addRow("Physical height (cm)", self.wizard_height_cm)
        tabs.addTab(basics, "1. Identity")

        timing = QWidget()
        timing_form = QFormLayout(timing)
        self.wizard_h_active = QSpinBox()
        self.wizard_h_active.setRange(320, 8192)
        self.wizard_h_active.setValue(1920)
        self.wizard_v_active = QSpinBox()
        self.wizard_v_active.setRange(200, 8192)
        self.wizard_v_active.setValue(1080)
        self.wizard_refresh = QSpinBox()
        self.wizard_refresh.setRange(24, 240)
        self.wizard_refresh.setValue(60)
        self.wizard_timing_mode = QComboBox()
        for label in ("cvt_rb", "cvt", "gtf", "automatic_hdtv"):
            self.wizard_timing_mode.addItem(label)
        timing_form.addRow("Native width", self.wizard_h_active)
        timing_form.addRow("Native height", self.wizard_v_active)
        timing_form.addRow("Refresh rate", self.wizard_refresh)
        timing_form.addRow("Timing formula", self.wizard_timing_mode)
        tabs.addTab(timing, "2. Native Mode")

        explain = QTextEdit()
        explain.setReadOnly(True)
        explain.setPlainText(
            "What the fields mean:\n\n"
            "- Manufacturer ID: three letters used in the EDID product ID.\n"
            "- Product code and serial: identify the display to Windows.\n"
            "- Physical size: used for DPI and display information.\n"
            "- Native mode: the preferred resolution and refresh rate.\n"
            "- Timing formula: reduced blanking is a safe default for modern flat panels.\n\n"
            "After creating the EDID, review the decoded text. Then save it or install it as a reversible Windows override."
        )
        tabs.addTab(explain, "3. Help")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        try:
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
            self.accept()
        except Exception as exc:
            log_exception("EDID creation wizard failed", exc)
            QMessageBox.critical(self, "EDID Creation Wizard", str(exc))


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
    from .resolutions import TimingMode, make_timing
    from .structured_edid import DetailedTiming

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


def _parse_hex_block(text: str) -> bytes:
    tokens = re.findall(r"0[xX]([0-9A-Fa-f]{2})|\b([0-9A-Fa-f]{2})\b", text)
    if not tokens:
        raise DisplayDataError("No hex bytes found.")
    return bytes(int(first or second, 16) for first, second in tokens)


def run_gui() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return int(app.exec())
