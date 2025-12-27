from __future__ import absolute_import, print_function, unicode_literals
import os
import subprocess
import logging
import sys
from maya import cmds

try:
    from PySide6 import QtWidgets, QtCore, QtGui  # type: ignore
    from PySide6.QtGui import QAction, QActionGroup
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui  # type: ignore
    from PySide2.QtWidgets import QAction, QActionGroup

from . import utils

# -------------------- Logging --------------------
LOG = logging.getLogger("LibraryUI")


# -------------------- Flow Layout --------------------
class FlowLayout(QtWidgets.QLayout):
    """Standard Qt FlowLayout implementation."""

    def __init__(self, parent=None, margin=0, hSpacing=-1, vSpacing=-1):
        super(FlowLayout, self).__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._hSpace = hSpacing
        self._vSpace = vSpacing
        self._itemList = []

    def addItem(self, item):
        self._itemList.append(item)

    def horizontalSpacing(self):
        if self._hSpace >= 0:
            return self._hSpace
        return self.smartSpacing(QtWidgets.QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._vSpace >= 0:
            return self._vSpace
        return self.smartSpacing(QtWidgets.QStyle.PM_LayoutVerticalSpacing)

    def count(self):
        return len(self._itemList)

    def itemAt(self, index):
        if 0 <= index < len(self._itemList):
            return self._itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._itemList):
            return self._itemList.pop(index)
        return None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._itemList:
            size = size.expandedTo(item.minimumSize())
        size += QtCore.QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacingX = self.horizontalSpacing()
        spacingY = self.verticalSpacing()

        for item in self._itemList:
            wid = item.widget()
            # Skip hidden widgets to prevent gaps
            if wid and not wid.isVisible():
                continue

            spaceX = spacingX
            spaceY = spacingY

            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

    def smartSpacing(self, pm):
        parent = self.parent()
        if parent is None:
            return 10
        elif parent.isWidgetType():
            try:
                return parent.style().pixelMetric(pm, None, parent)
            except Exception:
                return 10
        else:
            return parent.spacing()


# -------------------- Utility Widgets --------------------


class OpenMenu(QtWidgets.QMenu):
    def __init__(self, title=None, parent=None):
        super(OpenMenu, self).__init__(title, parent) if title else super(OpenMenu, self).__init__(parent)
        self.setSeparatorsCollapsible(False)
        if parent and hasattr(parent, "destroyed"):
            parent.destroyed.connect(self.close)
        self.triggered.connect(self._on_action_triggered)

    def _on_action_triggered(self, action):
        if isinstance(action, QtWidgets.QWidgetAction):
            return

    def showEvent(self, event):
        self._show_time = QtCore.QDateTime.currentMSecsSinceEpoch()
        self._show_pos = QtGui.QCursor.pos()
        super(OpenMenu, self).showEvent(event)

    def mouseReleaseEvent(self, e):
        # Prevent accidental trigger if menu was just opened via QPushButton click
        # Ignoring release if it's within 200ms and mouse hasn't moved much
        if hasattr(self, "_show_time"):
            time_diff = QtCore.QDateTime.currentMSecsSinceEpoch() - self._show_time
            pos_diff = (QtGui.QCursor.pos() - self._show_pos).manhattanLength()
            if time_diff < 200 and pos_diff < 5:
                return

        action = self.actionAt(e.pos())
        if action and action.isEnabled():
            action.setEnabled(False)
            super(OpenMenu, self).mouseReleaseEvent(e)
            action.setEnabled(True)
            action.trigger()
        else:
            super(OpenMenu, self).mouseReleaseEvent(e)


class FilterMenu(QtWidgets.QPushButton):
    """Button with a checkable menu for filtering."""

    selectionChanged = QtCore.Signal()

    def __init__(self, title, parent=None):
        super(FilterMenu, self).__init__(title, parent)
        self.menu = OpenMenu(self)
        self.setMenu(self.menu)

    def set_items(self, sections):
        self.menu.clear()
        if isinstance(sections, dict):
            for section_name in sections.keys():
                items = sections[section_name]
                self.menu.addSection(section_name)
                for item in items:
                    display_text = item.replace("&", "&&")
                    action = QAction(display_text, self.menu)
                    action.setData({"section": section_name, "value": item})
                    if item == "Empty":
                        font = action.font()
                        font.setItalic(True)
                        action.setFont(font)
                    action.setCheckable(True)
                    action.toggled.connect(self._on_change)
                    self.menu.addAction(action)

        self.menu.addSeparator()
        clear_action = QAction("Clear Filters", self.menu)
        clear_action.setIcon(utils.get_icon("trash.svg"))
        clear_action.triggered.connect(self.clear_selection)
        self.menu.addAction(clear_action)

    def _on_change(self, checked):
        self.selectionChanged.emit()

    def clear_selection(self):
        valid = False
        for action in self.menu.actions():
            if action.isCheckable() and action.isChecked():
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)
                valid = True
        if valid:
            self.selectionChanged.emit()

    def get_selected(self):
        selected = {}
        for action in self.menu.actions():
            if action.isCheckable() and action.isChecked():
                data = action.data()
                if data and isinstance(data, dict):
                    section = data.get("section")
                    value = data.get("value")
                    if section:
                        if section not in selected:
                            selected[section] = []
                        selected[section].append(value)
        return selected

    def set_selected(self, selected):
        if not isinstance(selected, dict):
            return
        for action in self.menu.actions():
            if action.isCheckable():
                data = action.data()
                if data and isinstance(data, dict):
                    section = data.get("section")
                    value = data.get("value")
                    should_check = False
                    if section and section in selected and value in selected[section]:
                        should_check = True

                    if action.isChecked() != should_check:
                        action.blockSignals(True)
                        action.setChecked(should_check)
                        action.blockSignals(False)


class SortMenu(QtWidgets.QPushButton):
    """Button with a menu for sorting options."""

    sortChanged = QtCore.Signal(str, bool)  # key, ascending

    def __init__(self, title="Sort", parent=None):
        super(SortMenu, self).__init__(title, parent)
        self.menu = OpenMenu(self)
        self.setMenu(self.menu)
        self._current_key = "Name"
        self._ascending = True
        self._setup_menu()

    def _setup_menu(self):
        self.menu.clear()

        # Sort Keys
        self.grp_keys = QActionGroup(self)
        self.grp_keys.setExclusive(True)

        for key in ["Name", "Collection", "Author"]:
            action = QAction(key, self.menu)
            action.setCheckable(True)
            action.setData(key)
            if key == self._current_key:
                action.setChecked(True)
            self.grp_keys.addAction(action)
            self.menu.addAction(action)

        self.grp_keys.triggered.connect(self._on_key_changed)

        self.menu.addSeparator()

        # Order
        self.grp_order = QActionGroup(self)
        self.grp_order.setExclusive(True)

        for text, val in [("Ascending", True), ("Descending", False)]:
            action = QAction(text, self.menu)
            action.setCheckable(True)
            action.setData(val)
            if val == self._ascending:
                action.setChecked(True)
            self.grp_order.addAction(action)
            self.menu.addAction(action)

        self.grp_order.triggered.connect(self._on_order_changed)

    def _on_key_changed(self, action):
        self._current_key = action.data()
        self.sortChanged.emit(self._current_key, self._ascending)
        self.setText("Sort: " + self._current_key)

    def _on_order_changed(self, action):
        self._ascending = action.data()
        self.sortChanged.emit(self._current_key, self._ascending)

    def set_sort(self, key, ascending):
        for action in self.grp_keys.actions():
            if action.data() == key:
                action.setChecked(True)
                self._current_key = key
                self.setText("Sort: " + self._current_key)
                break

        for action in self.grp_order.actions():
            if action.data() == ascending:
                action.setChecked(True)
                self._ascending = ascending
                break

    def get_current_sort(self):
        return self._current_key, self._ascending


class ClickableLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super(ClickableLabel, self).__init__(parent)
        self.setFixedSize(148, 148)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("border: 1px solid #444; background: #222; color: #888;")
        self._clickable = False

    def updateImageDisplay(self, object):
        """Standardizes image loading logic."""
        img_name = object.data.get("image") or utils.format_name(object.name) + ".jpg"
        img_path = os.path.join(utils.IMAGES_DIR, img_name)

        if img_name and os.path.exists(img_path):
            pix = QtGui.QPixmap(img_path)
            self.setPixmap(
                pix.scaled(
                    self.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
            )
            self.setCursor(QtCore.Qt.ArrowCursor)
            self._clickable = False
        else:
            self.setPixmap(QtGui.QPixmap())
            self.setText("{}\n(Click to set)".format(object.name))
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self._clickable = True

    def mousePressEvent(self, event):
        if self._clickable and event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super(ClickableLabel, self).mousePressEvent(event)


# -------------------- Main Widgets --------------------


class RigItemWidget(QtWidgets.QFrame):
    """Widget representing a single rig card in the grid."""

    imageUpdated = QtCore.Signal()
    filterRequested = QtCore.Signal(str, str)
    editRequested = QtCore.Signal(str)
    removeRequested = QtCore.Signal(str)
    refreshRequested = QtCore.Signal()

    def __init__(self, name, data, parent=None):
        super(RigItemWidget, self).__init__(parent)
        self.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        self.setFixedWidth(160)
        self.setFixedHeight(210)

        self.name = name
        self.data = data

        self._build_ui()
        self.update_state()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # Image
        self.image_lbl = ClickableLabel()
        self.image_lbl.clicked.connect(self.change_image)
        layout.addWidget(self.image_lbl)
        self.update_image_display()

        # Name
        self.name_lbl = QtWidgets.QLabel(self.name)
        self.name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.name_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.name_lbl)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.action_btn = QtWidgets.QPushButton("ADD")
        self.action_btn.setMinimumHeight(25)
        btn_layout.addWidget(self.action_btn, 2)

        self.info_btn = QtWidgets.QPushButton()
        self.info_btn.setIcon(utils.get_icon("info.svg"))
        self.info_btn.setFixedSize(25, 25)
        self.info_btn.clicked.connect(self.show_info)
        btn_layout.addWidget(self.info_btn, 0)

        layout.addLayout(btn_layout)
        self._formatTooltip()

    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.setTitle(self.name)
        menu.setTearOffEnabled(True)

        # Edit Actions
        edit_action = menu.addAction("Edit Details")
        edit_action.triggered.connect(lambda: self.editRequested.emit(self.name))

        menu.addSeparator()

        # File Actions
        action_open = menu.addAction("Open Rig Scene")
        action_open.setToolTip("Open this rig file in a new scene")
        action_open.triggered.connect(self._on_open_file)

        action_folder = menu.addAction("Show in Folder")
        action_folder.triggered.connect(self._on_show_in_folder)

        menu.addSeparator()

        # Destructive
        remove_action = menu.addAction("Remove Rig")
        remove_action.setIcon(utils.get_icon("trash.svg"))
        remove_action.triggered.connect(self._on_remove_request)

        menu.exec_(self.mapToGlobal(pos))

    def _on_open_file(self):
        path = self.data.get("path")
        if not path or not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Error", "File not found:\n" + str(path))
            return

        resp = QtWidgets.QMessageBox.warning(
            self,
            "Open Rig File",
            "This will open the rig source file in a NEW scene.\nUnsaved changes in the current scene will be lost.\n\nContinue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if resp == QtWidgets.QMessageBox.Yes:
            try:
                cmds.file(path, open=True, force=True)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to open file:\n" + str(e))
            self.refreshRequested.emit()

    def _on_show_in_folder(self):
        path = self.data.get("path")
        if not path:
            return

        path = os.path.normpath(path)
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Error", "File not found:\n" + path)
            return

        # Select file in explorer if possible
        if sys.platform == "win32":
            subprocess.Popen(r'explorer /select,"{}"'.format(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            # Linux usually just opens dir
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def _on_remove_request(self):
        resp = QtWidgets.QMessageBox.question(
            self,
            "Remove Rig",
            "Are you sure you want to remove '{}' from the library?\n\nThis will NOT delete files.".format(
                self.name
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if resp == QtWidgets.QMessageBox.Yes:
            self.removeRequested.emit(self.name)

    def _formatTooltip(self):
        tip = "Name: {}\n".format(self.name)
        tip += "Author: {}\n".format(self.data.get("author") or "Empty")
        tip += "Link: {}\n".format(self.data.get("link") or "Empty")
        tip += "Collection: {}\n".format(self.data.get("collection") or "Empty")
        tip += "Tags: {}\n".format(self.data.get("tags") or "Empty")
        path = self.data.get("path")
        if path:
            head, tail = os.path.split(path)
            path = ".../{}/{}".format(os.path.basename(head), tail)

        tip += "Path: {}".format(path or "Empty")
        self.setToolTip(tip)

    def update_image_display(self):
        self.image_lbl.updateImageDisplay(self)

    def change_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            new_name = utils.save_image_local(path, self.name)
            if new_name:
                self.data["image"] = new_name
                self.imageUpdated.emit()
                self.update_image_display()

    # ---------- State & Actions ----------

    def set_exists(self, exists):
        """Enable repathing if file missing, else enable usage."""
        self.action_btn.setEnabled(True)
        try:
            self.action_btn.clicked.disconnect()
        except Exception:
            pass

        if exists:
            # File exists, check if referenced
            self.update_state()
            self.action_btn.setToolTip(self.data.get("path", ""))
        else:
            # File missing
            self.action_btn.setText("MISSING")
            self.action_btn.setStyleSheet(
                "QPushButton { font-weight: bold; background-color: #444; color: #aaa; border: 1px solid #555; }"
                + "QPushButton:hover { background-color: #555; color: #eee; }"
            )
            self.action_btn.setToolTip("File not found. Click to repath.")
            self.action_btn.clicked.connect(self.repath_file)

    def repath_file(self):
        old_path = self.data.get("path", "")
        directory = os.path.dirname(old_path) if old_path else ""

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Locate Rig File", directory, "Maya Files (*.ma *.mb);;All Files (*.*)"
        )
        if path:
            self.data["path"] = path
            self.imageUpdated.emit()
            self.set_exists(True)

    def update_state(self):
        # Check current references in scene
        path = self.data.get("path", "")
        if not path:
            return

        norm_path = os.path.normpath(path).lower()
        is_ref = False
        try:
            refs = cmds.file(q=True, reference=True)
            for r in refs:
                if os.path.normpath(r).lower() == norm_path:
                    is_ref = True
                    break
        except Exception:
            pass

        try:
            self.action_btn.clicked.disconnect()
        except Exception:
            pass

        if is_ref:
            self.action_btn.setText("REMOVE")
            self.action_btn.setStyleSheet(
                "QPushButton { font-weight: bold; background-color: #733e3e; color: #ddd; }"
                + "QPushButton:hover { background-color: #8a4d4d; }"
                + "QPushButton:pressed { background-color: #6e2f2f; }"
            )
            self.action_btn.clicked.connect(self.remove_reference)
        else:
            self.action_btn.setText("ADD")
            self.action_btn.setStyleSheet(
                "QPushButton { font-weight: bold; background-color: #517853; color: white; }"
                + "QPushButton:disabled { background-color: #4e524e; }"
                + "QPushButton:hover { background-color: #608c62; }"
            )
            self.action_btn.clicked.connect(self.add_reference)

    def add_reference(self):
        path = self.data.get("path", "")
        if not path or not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Error", "File not found:\n" + path)
            return

        resp = cmds.confirmDialog(
            title="Add Reference",
            message="Add '{}' to scene?".format(self.name),
            button=["Reference", "Cancel"],
            defaultButton="Reference",
            cancelButton="Cancel",
            dismissString="Cancel",
        )
        if resp == "Reference":
            try:
                self.action_btn.setEnabled(False)
                cmds.file(path, reference=True, namespace=self.name.replace(" ", "_"))
                LOG.info("Referenced rig: {}".format(self.name))
            except Exception as e:
                LOG.error("Error referencing: {}".format(e))
                QtWidgets.QMessageBox.warning(self, "Error", str(e))
            finally:
                self.action_btn.setEnabled(True)
                self.update_state()

    def remove_reference(self):
        resp = cmds.confirmDialog(
            title="Remove Reference",
            message="Remove '{}'?".format(self.name),
            button=["Remove", "Cancel"],
            defaultButton="Cancel",
            cancelButton="Cancel",
        )
        if resp == "Remove":
            try:
                cmds.file(self.data.get("path"), removeReference=True)
                LOG.info("Removed reference: {}".format(self.name))
            except Exception as e:
                LOG.error("Remove failed: {}".format(e))
                QtWidgets.QMessageBox.warning(self, "Error", str(e))
            finally:
                self.update_state()

    def show_info(self):
        dlg = InfoDialog(self.name, self.data, self)
        dlg.filterRequested.connect(self.filterRequested.emit)
        dlg.editRequested.connect(lambda: self.editRequested.emit(self.name))
        dlg.exec_()


# -------------------- Info Dialog --------------------


class InfoDialog(QtWidgets.QDialog):
    filterRequested = QtCore.Signal(str, str)
    editRequested = QtCore.Signal()

    def __init__(self, name, data, parent=None):
        super(InfoDialog, self).__init__(parent)
        self.setWindowTitle(name)
        self.resize(300, 400)
        self.data = data
        self.name = name

        self._link_tmpl = '<a href="%s" style="color: #5285a6;">%s</a>'
        self._filter_tmpl = '<a href="%s" style="color: LightGray;">%s</a>'

        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Image
        self.image_lbl = QtWidgets.QLabel()
        self.image_lbl.setFixedSize(200, 200)
        self.image_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.image_lbl.setStyleSheet("background-color: #222; border: 1px solid #444;")

        img_name = self.data.get("image") or utils.format_name(self.name) + ".jpg"
        img_path = os.path.join(utils.IMAGES_DIR, img_name)

        if img_name and os.path.exists(img_path):
            pix = QtGui.QPixmap(img_path)
            self.image_lbl.setPixmap(
                pix.scaled(self.image_lbl.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            )
        else:
            self.image_lbl.setText("No Image")

        layout.addWidget(self.image_lbl, 0, QtCore.Qt.AlignHCenter)

        # Name
        name_lbl = QtWidgets.QLabel(self.name)
        name_lbl.setStyleSheet("font-weight: bold; font-size: 12pt;")
        name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(name_lbl)

        # Form Layout
        self.form_layout = QtWidgets.QFormLayout()
        self.form_layout.setLabelAlignment(QtCore.Qt.AlignRight)

        self._add_row("Author", self.data.get("author"), filter_cat="Author")
        self._add_row("Link", self.data.get("link"), is_link=True)
        self._add_row("Collection", self.data.get("collection"), filter_cat="Collections")
        self._add_row("Tags", self.data.get("tags", []), filter_cat="Tags")
        self._add_row("Path", self.data.get("path"), is_path=True)

        layout.addLayout(self.form_layout)
        layout.addStretch()

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        edit_btn = QtWidgets.QPushButton("Edit")
        edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(edit_btn)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _add_row(self, label, value, is_link=False, is_path=False, filter_cat=None):
        """Helper to add formatted rows to form layout."""
        if not value and not filter_cat:
            value = "Empty"

        lbl = QtWidgets.QLabel()
        lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        lbl.setWordWrap(True)

        if is_link and value != "Empty":
            href = value if value.startswith("http") else "http://" + value
            lbl.setText(self._link_tmpl % (href, href))
            lbl.setOpenExternalLinks(True)

        elif is_path and value != "Empty":
            lbl.setText(self._link_tmpl % (value, value))
            lbl.setToolTip("Click to open folder")
            lbl.linkActivated.connect(self._open_folder)

        elif filter_cat:
            # Handle list (Tags) or string (Collection)
            if isinstance(value, list):  # Tags
                if not value:
                    lbl.setText("Empty")
                else:
                    links = [self._filter_tmpl % (i, i) for i in value]
                    lbl.setText(", ".join(links))
                    lbl.linkActivated.connect(lambda v: self._emit_filter(filter_cat, v))
            else:  # Collection/Author
                disp = value if value else "Empty"
                filt = value if value else "Empty"
                if disp == "Empty":
                    disp = "<i>Empty</i>"

                lbl.setText(self._filter_tmpl % (filt, disp))
                lbl.linkActivated.connect(lambda v: self._emit_filter(filter_cat, v))
        else:
            lbl.setText(str(value))
            lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        self.form_layout.addRow(label + ":", lbl)

    def _emit_filter(self, cat, val):
        self.filterRequested.emit(cat, val)
        self.accept()

    def _on_edit(self):
        self.editRequested.emit()
        self.accept()

    def _open_folder(self, path):
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return

        if sys.platform == "win32":
            subprocess.Popen(r'explorer /select,"{}"'.format(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            # Fallback for linux or generic dir opening
            target = os.path.dirname(path) if os.path.isfile(path) else path
            subprocess.Popen(["xdg-open", target])


# -------------------- Edit Dialog --------------------


class TagsLineEdit(QtWidgets.QLineEdit):
    """QLineEdit with comma-separated auto-completion."""

    def __init__(self, tags, parent=None):
        super(TagsLineEdit, self).__init__(parent)
        self.completer = QtWidgets.QCompleter(tags, self)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.completer.setWidget(self)
        self.completer.activated.connect(self.insert_completion)

    def keyPressEvent(self, event):
        super(TagsLineEdit, self).keyPressEvent(event)

        text = self.text()[: self.cursorPosition()]
        if not text:
            self.completer.popup().hide()
            return

        prefix = text.split(",")[-1].strip()
        if prefix:
            self.completer.setCompletionPrefix(prefix)
            if self.completer.completionCount() > 0:
                rect = self.cursorRect()
                rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 10)
                self.completer.complete(rect)
            else:
                self.completer.popup().hide()
        else:
            self.completer.popup().hide()

    def insert_completion(self, completion):
        completion = str(completion)
        text = self.text()
        pos = self.cursorPosition()

        # Find the start of the current tag being edited
        start_index = text.rfind(",", 0, pos) + 1

        # Check if we need to add a separator after completion
        remaining = text[pos:]
        separator = ", "
        if remaining.lstrip().startswith(","):
            separator = ""

        # Construct new text
        new_text = text[:start_index] + " " + completion + separator + remaining

        # Clean up
        new_text = new_text.replace("  ", " ")
        if new_text.startswith(" "):
            new_text = new_text[1:]

        self.setText(new_text)
        self.setCursorPosition(len(new_text) - len(remaining))


class RigSetupDialog(QtWidgets.QDialog):
    """Dialog for Adding or Editing a rig."""

    def __init__(
        self,
        existing_names,
        collections,
        authors,
        tags,
        mode="add",
        rig_name=None,
        rig_data=None,
        file_path=None,
        parent=None,
    ):
        super(RigSetupDialog, self).__init__(parent)
        self.mode = mode
        self.rig_name = rig_name
        self.rig_data = rig_data or {}
        self.existing_names = existing_names
        # Ensure autocomplete lists are lists
        self.collections = list(collections)
        self.authors = list(authors)
        self.tags = list(tags)

        self.file_path = file_path or self.rig_data.get("path", "")
        self.image_path = ""
        self.result_data = None

        self.setWindowTitle("Edit Rig" if mode == "edit" else "Add New Rig")
        self.resize(300, 480)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # Image
        self.image_lbl = QtWidgets.QLabel("No Image\n(Click to set)")
        self.image_lbl.setFixedSize(150, 150)
        self.image_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.image_lbl.setStyleSheet("background-color: #222; border: 1px solid #555; border-radius: 5px;")
        self.image_lbl.setCursor(QtCore.Qt.PointingHandCursor)
        self.image_lbl.mousePressEvent = self.on_image_click

        # Load existing image
        cur_img = self.rig_data.get("image")
        if cur_img:
            p = os.path.join(utils.IMAGES_DIR, cur_img)
            if os.path.exists(p):
                self.image_lbl.setText("")
                pix = QtGui.QPixmap(p).scaled(
                    150, 150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                )
                self.image_lbl.setPixmap(pix)

        layout.addWidget(self.image_lbl, 0, QtCore.Qt.AlignHCenter)

        # Form
        form = QtWidgets.QFormLayout()

        # Name
        self.name_input = QtWidgets.QLineEdit()
        if self.mode == "edit":
            self.name_input.setText(self.rig_name)
        else:
            self.name_input.setText(os.path.splitext(os.path.basename(self.file_path))[0])
        self.name_input.textChanged.connect(self.validate_name)
        form.addRow("Name:", self.name_input)

        # Tags
        orig_tags = self.rig_data.get("tags", [])
        tag_str = ", ".join(orig_tags) if isinstance(orig_tags, list) else (orig_tags or "")
        self.tags_input = TagsLineEdit(self.tags)
        self.tags_input.setText(tag_str)
        self.tags_input.setPlaceholderText("human, biped, prop...")
        form.addRow("Tags:", self.tags_input)

        # Collection
        self.coll_input = QtWidgets.QLineEdit()
        if self.collections:
            comp = QtWidgets.QCompleter(self.collections)
            comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.coll_input.setCompleter(comp)
        coll_val = self.rig_data.get("collection") or ""
        self.coll_input.setText("" if coll_val == "Empty" else coll_val)
        form.addRow("Collection:", self.coll_input)

        # Author
        self.auth_input = QtWidgets.QLineEdit()
        if self.authors:
            comp = QtWidgets.QCompleter(self.authors)
            comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.auth_input.setCompleter(comp)
        auth_val = self.rig_data.get("author") or ""
        self.auth_input.setText("" if auth_val == "Empty" else auth_val)
        form.addRow("Author:", self.auth_input)

        # Link
        self.link_input = QtWidgets.QLineEdit()
        link_val = self.rig_data.get("link") or ""
        self.link_input.setText("" if link_val == "Empty" else link_val)
        form.addRow("Link:", self.link_input)

        layout.addLayout(form)
        layout.addStretch()

        # Footer Buttons
        btns = QtWidgets.QHBoxLayout()
        self.ok_btn = QtWidgets.QPushButton("Save" if self.mode == "edit" else "Add")
        self.ok_btn.clicked.connect(self.accept_data)
        btns.addWidget(self.ok_btn)

        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        self.validate_name()

    def on_image_click(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.webp)"
            )
            if path:
                self.image_path = path
                pix = QtGui.QPixmap(path).scaled(
                    150, 150, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                )
                self.image_lbl.setPixmap(pix)
                self.image_lbl.setText("")

    def validate_name(self):
        name = self.name_input.text().strip()
        valid = True
        msg = ""

        if not name:
            valid = False
            msg = "Name required"
        elif name in self.existing_names and name != self.rig_name:
            valid = False
            msg = "Name taken"

        self.ok_btn.setEnabled(valid)
        self.ok_btn.setToolTip(msg)

    def accept_data(self):
        name = self.name_input.text().strip()
        tags = list(set([t.strip() for t in self.tags_input.text().split(",") if t.strip()]))

        # Image handling
        img_name = self.rig_data.get("image", "")
        if self.image_path and os.path.exists(self.image_path):
            res = utils.save_image_local(self.image_path, name)
            if res:
                img_name = res

        self.result_data = {
            "name": name,
            "data": {
                "path": self.file_path,
                "image": img_name,
                "tags": tags,  # Do not force to "Empty" string if empty list, keep list
                "collection": self.coll_input.text().strip() or "Empty",
                "author": self.auth_input.text().strip() or "Empty",
                "link": self.link_input.text().strip() or "Empty",
            },
        }
        self.accept()
