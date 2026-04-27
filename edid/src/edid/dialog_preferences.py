from __future__ import annotations

from typing import Final

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required for dialog preferences. Install it with: pip install PySide6") from exc


_ROOT_GROUP: Final[str] = "dialogs"
_KNOWN_KEYS: Final[str] = f"{_ROOT_GROUP}/known_keys"
_known_labels: dict[str, str] = {}


def _settings() -> QSettings:
    return QSettings()


def register_dialog(key: str, label: str) -> None:
    _known_labels[key] = label
    settings = _settings()
    keys = [str(item) for item in settings.value(_KNOWN_KEYS, [], type=list) or []]
    if key not in keys:
        keys.append(key)
        settings.setValue(_KNOWN_KEYS, keys)


def _dialog_group(key: str) -> str:
    return f"{_ROOT_GROUP}/{key}"


def _is_suppressed(key: str) -> bool:
    return bool(_settings().value(f"{_dialog_group(key)}/suppressed", False, type=bool))


def _set_suppressed(key: str, value: bool) -> None:
    _settings().setValue(f"{_dialog_group(key)}/suppressed", bool(value))


def _stored_response(key: str) -> int:
    return int(_settings().value(f"{_dialog_group(key)}/response", int(QMessageBox.StandardButton.No), type=int))


def _set_stored_response(key: str, response: int) -> None:
    _settings().setValue(f"{_dialog_group(key)}/response", int(response))


def show_yes_no(
    parent: QWidget | None,
    *,
    key: str,
    title: str,
    text: str,
    default: QMessageBox.StandardButton = QMessageBox.StandardButton.No,
    label: str | None = None,
) -> bool:
    register_dialog(key, label or title)
    if _is_suppressed(key):
        return _stored_response(key) == int(QMessageBox.StandardButton.Yes)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(default)
    never = QCheckBox("Never show again")
    box.setCheckBox(never)
    result = box.exec()
    if never.isChecked():
        _set_suppressed(key, True)
        _set_stored_response(key, int(result))
    return result == int(QMessageBox.StandardButton.Yes)


def show_message(
    parent: QWidget | None,
    *,
    key: str,
    title: str,
    text: str,
    icon: QMessageBox.Icon,
    label: str | None = None,
) -> None:
    register_dialog(key, label or title)
    if _is_suppressed(key):
        return
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    never = QCheckBox("Never show again")
    box.setCheckBox(never)
    box.exec()
    if never.isChecked():
        _set_suppressed(key, True)
        _set_stored_response(key, int(QMessageBox.StandardButton.Ok))


def reset_all_dialogs() -> None:
    settings = _settings()
    keys = [str(item) for item in settings.value(_KNOWN_KEYS, [], type=list) or []]
    for key in keys:
        settings.remove(_dialog_group(key))


class DialogPreferencesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(620, 420)
        self._list = QListWidget(self)
        self._hint = QLabel("Checked items are currently suppressed (Never show again).", self)
        self._hint.setWordWrap(True)
        self._reset_button = QPushButton("Re-enable all dialogs", self)
        self._reset_button.clicked.connect(self._reset_all)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)

        controls = QHBoxLayout()
        controls.addWidget(self._reset_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hint)
        layout.addWidget(self._list, 1)
        layout.addLayout(controls)
        layout.addWidget(button_box)

        self._populate()
        self._list.itemChanged.connect(self._item_changed)

    def _all_keys(self) -> list[str]:
        settings = _settings()
        known = [str(item) for item in settings.value(_KNOWN_KEYS, [], type=list) or []]
        return sorted(set(known).union(_known_labels))

    def _populate(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for key in self._all_keys():
            label = _known_labels.get(key, key)
            item = QListWidgetItem(f"{label} [{key}]")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setCheckState(Qt.CheckState.Checked if _is_suppressed(key) else Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _item_changed(self, item: QListWidgetItem) -> None:
        key = str(item.data(Qt.ItemDataRole.UserRole))
        _set_suppressed(key, item.checkState() == Qt.CheckState.Checked)

    def _reset_all(self) -> None:
        reset_all_dialogs()
        self._populate()

