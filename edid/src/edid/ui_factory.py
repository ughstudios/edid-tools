from __future__ import annotations

import ast
from pathlib import Path
import xml.etree.ElementTree as ET
import shutil

try:
    from PySide6.QtGui import QAction
    from PySide6.QtCore import QSize, Qt
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
        QMenu,
        QMenuBar,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QSplitter,
        QStackedWidget,
        QStyle,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        QWizard,
        QWizardPage,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required for XML UI loading. Install it with: pip install PySide6") from exc


class UiFactoryError(RuntimeError):
    """Raised when XML UI loading fails."""


class XmlUi:
    def __init__(self, root: QWidget, widgets: dict[str, object]) -> None:
        self.root = root
        self.widgets = widgets

    def __getitem__(self, name: str) -> object:
        return self.widgets[name]


class _LoadContext:
    def __init__(self, owner: object | None = None, window: object | None = None) -> None:
        self.owner = owner
        self.window = window


def xml_root_dir() -> Path:
    root = Path(__file__).resolve().parents[2] / "xml"
    _seed_xml_assets(root)
    return root


def _seed_xml_assets(target_dir: Path) -> None:
    legacy_dir = Path(__file__).resolve().parent / "ui"
    if not legacy_dir.is_dir():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in legacy_dir.glob("*.xml"):
        destination = target_dir / source.name
        if destination.is_file():
            continue
        shutil.copy2(source, destination)


def load_ui(path: str | Path, *, owner: object | None = None, window: object | None = None) -> XmlUi:
    xml_path = Path(path)
    root_element = ET.parse(xml_path).getroot()
    widgets: dict[str, object] = {}
    context = _LoadContext(owner=owner, window=window)
    root_widget = _build_widget(root_element, widgets, xml_path.parent, context)
    if not isinstance(root_widget, QWidget):
        raise UiFactoryError("Root XML element must create a QWidget.")
    ui = XmlUi(root_widget, widgets)
    for name, widget in widgets.items():
        setattr(ui, name, widget)
    return ui


def _build_widget(element: ET.Element, widgets: dict[str, object], base_dir: Path, context: _LoadContext) -> object:
    if element.tag == "include":
        element = _load_include(element, base_dir)
    tag = element.tag
    if tag == "menu_bar":
        return _build_menu_bar(element, widgets, base_dir, context)
    if tag == "menu":
        return _build_menu(element, widgets, base_dir, context)
    if tag == "action":
        return _build_action(element, widgets, context)
    if tag == "widget":
        widget = _create_widget(element)
        _register(element, widget, widgets)
        _apply_common_properties(element, widget)
        _connect_declared_signals(element, widget, context)
        _populate_widget(widget, element, widgets, base_dir, context)
        return widget
    if tag == "tabs":
        tabs = QTabWidget()
        _register(element, tabs, widgets)
        _connect_declared_signals(element, tabs, context)
        for child in element:
            if child.tag != "tab":
                raise UiFactoryError("tabs can only contain tab children.")
            page = QWidget()
            _register(child, page, widgets)
            _apply_common_properties(child, page)
            _connect_declared_signals(child, page, context)
            for layout_child in child:
                if layout_child.tag == "include":
                    layout_child = _load_include(layout_child, base_dir)
                page.setLayout(_build_layout(layout_child, widgets, base_dir, context))
            index = tabs.addTab(page, child.attrib.get("title", "Tab"))
            tip = child.attrib.get("tooltip")
            if tip:
                tabs.tabBar().setTabToolTip(index, tip)
        return tabs
    if tag == "stack":
        stack = QStackedWidget()
        _register(element, stack, widgets)
        _connect_declared_signals(element, stack, context)
        for child in element:
            page = _build_widget(child, widgets, base_dir, context)
            if not isinstance(page, QWidget):
                raise UiFactoryError("stack children must be widgets.")
            stack.addWidget(page)
        return stack
    if tag == "splitter":
        return _build_splitter(element, widgets, base_dir, context)
    widget = _create_widget(element)
    _register(element, widget, widgets)
    _apply_common_properties(element, widget)
    _connect_declared_signals(element, widget, context)
    _populate_widget(widget, element, widgets, base_dir, context)
    return widget


def _populate_widget(widget: QWidget, element: ET.Element, widgets: dict[str, object], base_dir: Path, context: _LoadContext) -> None:
    if isinstance(widget, QWizard):
        for child in element:
            if child.tag == "include":
                child = _load_include(child, base_dir)
            if child.tag != "wizard_page":
                raise UiFactoryError(f"QWizard children must be wizard_page, got {child.tag!r}.")
            page = QWizardPage()
            _register(child, page, widgets)
            title = child.attrib.get("title", "")
            if title:
                page.setTitle(title)
            subtitle = child.attrib.get("subtitle", "")
            if subtitle:
                page.setSubTitle(subtitle)
            inner = list(child)
            if len(inner) != 1:
                raise UiFactoryError("wizard_page must have exactly one layout child.")
            layout_el = inner[0]
            if layout_el.tag == "include":
                layout_el = _load_include(layout_el, base_dir)
            if layout_el.tag not in {"vbox", "hbox", "grid", "form"}:
                raise UiFactoryError("wizard_page child must be vbox, hbox, grid, or form.")
            page.setLayout(_build_layout(layout_el, widgets, base_dir, context))
            widget.addPage(page)
        return
    for child in element:
        if child.tag == "include":
            child = _load_include(child, base_dir)
        if child.tag == "menu_bar":
            menu_bar = _build_menu_bar(child, widgets, base_dir, context)
            if context.window is not None and hasattr(context.window, "setMenuBar"):
                context.window.setMenuBar(menu_bar)
            elif widget.layout() is None:
                widget.setLayout(QVBoxLayout())
                widget.layout().addWidget(menu_bar)
            else:
                widget.layout().setMenuBar(menu_bar)
            continue
        if child.tag in {"vbox", "hbox", "grid", "form"}:
            widget.setLayout(_build_layout(child, widgets, base_dir, context))
        elif child.tag in {
            "widget",
            "tabs",
            "stack",
            "splitter",
            "QLabel",
            "QPushButton",
            "QComboBox",
            "QTextEdit",
            "QPlainTextEdit",
            "QLineEdit",
            "QCheckBox",
            "QSpinBox",
            "QListWidget",
            "QGroupBox",
            "QDialogButtonBox",
            "QScrollArea",
        }:
            child_widget = _build_widget(child, widgets, base_dir, context)
            if widget.layout() is None:
                widget.setLayout(QVBoxLayout())
            widget.layout().addWidget(child_widget)
        else:
            raise UiFactoryError(f"Unsupported child {child.tag!r} under {element.tag!r}.")


def _build_splitter(element: ET.Element, widgets: dict[str, object], base_dir: Path, context: _LoadContext) -> QSplitter:
    orient = element.attrib.get("orientation", "horizontal").lower()
    if orient == "vertical":
        splitter = QSplitter(Qt.Orientation.Vertical)
    else:
        splitter = QSplitter(Qt.Orientation.Horizontal)
    _register(element, splitter, widgets)
    _apply_common_properties(element, splitter)
    _connect_declared_signals(element, splitter, context)
    if element.attrib.get("childrenCollapsible", "false").lower() != "true":
        splitter.setChildrenCollapsible(False)
    for child in element:
        if child.tag == "include":
            child = _load_include(child, base_dir)
        if child.tag in {"vbox", "hbox", "grid", "form"}:
            pane = QWidget()
            pane.setLayout(_build_layout(child, widgets, base_dir, context))
            _register(child, pane.layout(), widgets)
            item: QWidget = pane
        else:
            built = _build_widget(child, widgets, base_dir, context)
            if not isinstance(built, QWidget):
                raise UiFactoryError(f"splitter child {child.tag!r} did not produce QWidget")
            item = built
        splitter.addWidget(item)
        idx = splitter.count() - 1
        stretch_factor = int(child.attrib.get("stretch", "0") or "0")
        if stretch_factor > 0:
            splitter.setStretchFactor(idx, stretch_factor)
    sizes_raw = element.attrib.get("sizes", "").strip()
    if sizes_raw:
        sizes = [int(part.strip()) for part in sizes_raw.split(",") if part.strip()]
        if len(sizes) == splitter.count() and splitter.count() > 0:
            splitter.setSizes(sizes)
    elif splitter.count() == 3 and all(splitter.stretchFactor(index) == 0 for index in range(3)):
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
    return splitter


def _build_menu_bar(element: ET.Element, widgets: dict[str, object], base_dir: Path, context: _LoadContext) -> QMenuBar:
    menu_bar = QMenuBar()
    _register(element, menu_bar, widgets)
    _apply_common_properties(element, menu_bar)
    for child in element:
        if child.tag == "include":
            child = _load_include(child, base_dir)
        if child.tag != "menu":
            raise UiFactoryError(f"menu_bar children must be menu, got {child.tag!r}.")
        menu_bar.addMenu(_build_menu(child, widgets, base_dir, context))
    return menu_bar


def _build_menu(element: ET.Element, widgets: dict[str, object], base_dir: Path, context: _LoadContext) -> QMenu:
    menu = QMenu(element.attrib.get("title") or element.attrib.get("text", ""))
    _register(element, menu, widgets)
    _apply_common_properties(element, menu)
    for child in element:
        if child.tag == "include":
            child = _load_include(child, base_dir)
        if child.tag == "separator":
            menu.addSeparator()
        elif child.tag == "menu":
            menu.addMenu(_build_menu(child, widgets, base_dir, context))
        elif child.tag == "action":
            menu.addAction(_build_action(child, widgets, context))
        else:
            raise UiFactoryError(f"Unsupported child {child.tag!r} under menu.")
    return menu


def _build_action(element: ET.Element, widgets: dict[str, object], context: _LoadContext) -> QAction:
    action = QAction(element.attrib.get("text", ""))
    _register(element, action, widgets)
    _apply_common_properties(element, action)
    _connect_declared_signals(element, action, context)
    return action


def _build_layout(element: ET.Element, widgets: dict[str, object], base_dir: Path, context: _LoadContext) -> object:
    if element.tag == "include":
        element = _load_include(element, base_dir)
    if element.tag == "vbox":
        layout = QVBoxLayout()
    elif element.tag == "hbox":
        layout = QHBoxLayout()
    elif element.tag == "grid":
        layout = QGridLayout()
    elif element.tag == "form":
        layout = QFormLayout()
    else:
        raise UiFactoryError(f"Unsupported layout {element.tag!r}.")

    _register(element, layout, widgets)
    _apply_layout_properties(element, layout)
    for child in element:
        if child.tag == "include":
            child = _load_include(child, base_dir)
        if child.tag == "stretch":
            layout.addStretch(int(child.attrib.get("value", "1")))
            continue
        if child.tag == "splitter":
            splitter = _build_splitter(child, widgets, base_dir, context)
            stretch = int(child.attrib.get("stretch", "0"))
            if isinstance(layout, QGridLayout):
                row = int(child.attrib.get("row", "0"))
                column = int(child.attrib.get("column", "0"))
                row_span = int(child.attrib.get("rowspan", "1"))
                column_span = int(child.attrib.get("colspan", "1"))
                layout.addWidget(splitter, row, column, row_span, column_span)
            else:
                layout.addWidget(splitter, stretch)
            continue
        if child.tag == "row" and isinstance(layout, QFormLayout):
            label = child.attrib.get("label", "")
            if len(child):
                layout.addRow(label, _build_widget(child[0], widgets, base_dir, context))
            continue
        if child.tag in {"vbox", "hbox", "grid", "form"}:
            item = QWidget()
            item.setLayout(_build_layout(child, widgets, base_dir, context))
            _register(child, item.layout(), widgets)
        else:
            item = _build_widget(child, widgets, base_dir, context)
        if isinstance(layout, QGridLayout):
            row = int(child.attrib.get("row", "0"))
            column = int(child.attrib.get("column", "0"))
            row_span = int(child.attrib.get("rowspan", "1"))
            column_span = int(child.attrib.get("colspan", "1"))
            layout.addWidget(item, row, column, row_span, column_span)
        else:
            stretch = int(child.attrib.get("stretch", "0"))
            layout.addWidget(item, stretch)
    if element.tag == "grid" and isinstance(layout, QGridLayout):
        columnstretch = element.attrib.get("columnstretch", "").strip()
        if columnstretch:
            for index, part in enumerate(columnstretch.split(",")):
                part = part.strip()
                if part:
                    layout.setColumnStretch(index, int(part))
    return layout


def _create_widget(element: ET.Element) -> QWidget:
    tag = element.tag
    if tag == "widget":
        class_name = element.attrib.get("class", "QWidget")
    else:
        class_name = tag
    mapping = {
        "QDialog": QDialog,
        "QWizard": QWizard,
        "QWidget": QWidget,
        "QLabel": QLabel,
        "QPushButton": QPushButton,
        "QComboBox": QComboBox,
        "QTextEdit": QTextEdit,
        "QPlainTextEdit": QPlainTextEdit,
        "QLineEdit": QLineEdit,
        "QCheckBox": QCheckBox,
        "QSpinBox": QSpinBox,
        "QListWidget": QListWidget,
        "QGroupBox": QGroupBox,
        "QDialogButtonBox": QDialogButtonBox,
        "QScrollArea": QScrollArea,
    }
    if class_name not in mapping:
        raise UiFactoryError(f"Unsupported widget class {class_name!r}.")
    if class_name == "QDialog":
        widget = QDialog()
    elif class_name == "QWizard":
        widget = QWizard()
    elif class_name == "QDialogButtonBox":
        widget = QDialogButtonBox(_button_box_flags(element.attrib.get("buttons", "")))
    elif class_name in {"QLabel", "QPushButton", "QCheckBox", "QGroupBox"}:
        widget = mapping[class_name](element.attrib.get("text") or element.attrib.get("title", ""))
    else:
        widget = mapping[class_name]()
    _apply_common_properties(element, widget)
    return widget


def _load_include(element: ET.Element, base_dir: Path) -> ET.Element:
    file_name = element.attrib.get("file")
    if not file_name:
        raise UiFactoryError("include requires a file attribute.")
    return ET.parse(base_dir / file_name).getroot()


def _register(element: ET.Element, widget: object, widgets: dict[str, object]) -> None:
    name = element.attrib.get("name")
    if name:
        widgets[name] = widget


def _apply_common_properties(element: ET.Element, widget: object) -> None:
    if "objectName" in element.attrib and hasattr(widget, "setObjectName"):
        widget.setObjectName(element.attrib["objectName"])
    elif "name" in element.attrib and hasattr(widget, "setObjectName"):
        widget.setObjectName(element.attrib["name"])
    if "tooltip" in element.attrib and hasattr(widget, "setToolTip"):
        widget.setToolTip(element.attrib["tooltip"])
    if "placeholder" in element.attrib and hasattr(widget, "setPlaceholderText"):
        widget.setPlaceholderText(element.attrib["placeholder"])
    if element.attrib.get("readonly") == "true" and hasattr(widget, "setReadOnly"):
        widget.setReadOnly(True)
    if element.attrib.get("wordWrap") == "true" and hasattr(widget, "setWordWrap"):
        widget.setWordWrap(True)
    if element.attrib.get("openExternalLinks") == "true" and hasattr(widget, "setOpenExternalLinks"):
        widget.setOpenExternalLinks(True)
    if "text" in element.attrib and hasattr(widget, "setText") and not isinstance(widget, (QPushButton, QCheckBox, QGroupBox)):
        widget.setText(element.attrib["text"])
    if "title" in element.attrib and hasattr(widget, "setWindowTitle"):
        widget.setWindowTitle(element.attrib["title"])
    if "icon" in element.attrib and isinstance(widget, QPushButton):
        icon_name = element.attrib["icon"]
        if hasattr(QStyle, icon_name):
            widget.setIcon(widget.style().standardIcon(getattr(QStyle, icon_name)))
            widget.setIconSize(QSize(18, 18))
    if "min" in element.attrib and hasattr(widget, "setMinimum"):
        widget.setMinimum(int(element.attrib["min"]))
    if "max" in element.attrib and hasattr(widget, "setMaximum"):
        widget.setMaximum(int(element.attrib["max"]))
    if "value" in element.attrib and hasattr(widget, "setValue"):
        widget.setValue(int(element.attrib["value"]))
    if element.attrib.get("echoMode") == "password" and hasattr(widget, "setEchoMode"):
        widget.setEchoMode(QLineEdit.Password)
    if isinstance(widget, QScrollArea):
        widget.setWidgetResizable(element.attrib.get("widgetResizable", "true") != "false")


def _apply_layout_properties(element: ET.Element, layout: object) -> None:
    if "spacing" in element.attrib and hasattr(layout, "setSpacing"):
        layout.setSpacing(int(element.attrib["spacing"]))
    if "margins" in element.attrib and hasattr(layout, "setContentsMargins"):
        values = [int(value) for value in element.attrib["margins"].split(",")]
        if len(values) == 4:
            layout.setContentsMargins(*values)


def _connect_declared_signals(element: ET.Element, target: object, context: _LoadContext) -> None:
    if context.owner is None and context.window is None:
        return
    for attr_name, expression in element.attrib.items():
        if not attr_name.startswith("on_"):
            continue
        signal_name = attr_name[3:]
        signal = getattr(target, signal_name, None)
        if signal is None or not hasattr(signal, "connect"):
            raise UiFactoryError(f"{element.tag} {element.attrib.get('name', '')!r} has no signal {signal_name!r}.")
        signal.connect(safe_eval(expression, owner=context.owner, window=context.window))


def safe_eval(expression: str, *, owner: object | None, window: object | None = None) -> object:
    """Resolve a constrained XML callback expression into a zero-argument slot."""
    try:
        node = ast.parse(expression, mode="eval").body
        if isinstance(node, ast.Call):
            target = _resolve_callable(node.func, owner=owner, window=window)
            args = [_literal_value(arg) for arg in node.args]
            kwargs = {}
            for keyword in node.keywords:
                if keyword.arg is None:
                    raise UiFactoryError("Callback expressions do not support **kwargs.")
                kwargs[keyword.arg] = _literal_value(keyword.value)

            def call_with_literals(*_signal_args: object) -> object:
                return target(*args, **kwargs)

            return call_with_literals
        target = _resolve_callable(node, owner=owner, window=window)

        def call_reference(*_signal_args: object) -> object:
            return target()

        return call_reference
    except (AttributeError, SyntaxError, ValueError, TypeError, UiFactoryError) as exc:
        raise UiFactoryError(f"Invalid callback expression {expression!r}: {exc}") from exc


def _resolve_callable(node: ast.AST, *, owner: object | None, window: object | None) -> object:
    target = _resolve_value(node, owner=owner, window=window)
    if not callable(target):
        raise UiFactoryError(f"Callback target {ast.unparse(node)!r} is not callable.")
    return target


def _resolve_value(node: ast.AST, *, owner: object | None, window: object | None) -> object:
    if isinstance(node, ast.Name):
        if node.id in {"self", "owner"}:
            if owner is None:
                raise UiFactoryError("Callback expression requires an owner.")
            return owner
        if node.id == "window":
            if window is None:
                raise UiFactoryError("Callback expression requires a window.")
            return window
        if owner is None:
            raise UiFactoryError("Callback expression requires an owner.")
        if node.id.startswith("__"):
            raise UiFactoryError("Callback attributes cannot be dunder names.")
        return getattr(owner, node.id)
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("__"):
            raise UiFactoryError("Callback attributes cannot be dunder names.")
        value = _resolve_value(node.value, owner=owner, window=window)
        return getattr(value, node.attr)
    raise UiFactoryError("Callback expressions must be a method name or method call.")


def _literal_value(node: ast.AST) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError) as exc:
        raise UiFactoryError("Callback arguments must be Python literals.") from exc


def _button_box_flags(value: str) -> QDialogButtonBox.StandardButton:
    flags = QDialogButtonBox.StandardButton(0)
    mapping = {
        "Ok": QDialogButtonBox.Ok,
        "Cancel": QDialogButtonBox.Cancel,
        "Apply": QDialogButtonBox.Apply,
        "Close": QDialogButtonBox.Close,
        "Yes": QDialogButtonBox.Yes,
        "No": QDialogButtonBox.No,
    }
    for item in value.split("|"):
        item = item.strip()
        if item in mapping:
            flags |= mapping[item]
    return flags
