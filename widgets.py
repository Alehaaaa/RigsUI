import os
import subprocess
import logging
import sys
import json
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

CONTEXTUAL_CURSOR = QtGui.QCursor(QtGui.QPixmap(":/rmbMenu.png"), hotX=11, hotY=8)


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

    def addWidget(self, widget):
        self.addItem(QtWidgets.QWidgetItem(widget))
        widget.setParent(self.parentWidget())
        self.invalidate()

    def insertWidget(self, index, widget):
        widget.setParent(self.parentWidget())
        item = QtWidgets.QWidgetItem(widget)
        self._itemList.insert(index, item)
        self.invalidate()

    def insertItem(self, index, item):
        self._itemList.insert(index, item)
        self.invalidate()

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
        self._base_title = title
        self._update_button_text()

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
        self._update_button_text()

    def _on_change(self, checked):
        self._update_button_text()
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
            self._update_button_text()
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
        self._update_button_text()

    def _update_button_text(self):
        selected = self.get_selected()
        count = sum(len(vals) for vals in selected.values())
        self.setText("{} ({})".format(self._base_title, count))


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
    dataChanged = QtCore.Signal(str, object)  # key, value
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

    def update_data(self, data):
        """Updates internal data and refreshes UI."""
        self.data = data
        self.update_image_display()
        self.set_exists(data.get("exists", True))
        self._formatTooltip()

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
        self.info_btn.setCursor(CONTEXTUAL_CURSOR)
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
        edit_action.setIcon(utils.get_icon("edit.svg"))
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
                self.dataChanged.emit("image", new_name)

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
            self.dataChanged.emit("path", path)

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
        self._curr_info_dlg = InfoDialog(self.name, self.data, self)
        self._curr_info_dlg.filterRequested.connect(self.filterRequested.emit)
        self._curr_info_dlg.editRequested.connect(lambda: self.editRequested.emit(self.name))
        self._curr_info_dlg.exec_()
        self._curr_info_dlg = None

    def close_info_dialog(self):
        """Force close the info dialog if open."""
        if getattr(self, "_curr_info_dlg", None):
            self._curr_info_dlg.accept()



class ElidedClickableLabel(QtWidgets.QLabel):
    """Label that elides text from the left and supports clicking."""
    clicked = QtCore.Signal()

    def __init__(self, text, parent=None):
        super(ElidedClickableLabel, self).__init__(text, parent)
        self._full_text = text
        # Expanding allows shrinking down to minimumSizeHint, unlike MinimumExpanding which uses sizeHint as minimum
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(text)

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self.updateGeometry()
        self.update()

    def minimumSizeHint(self):
        # Allow shrinking very small so window isn't forced wide
        return QtCore.QSize(10, super(ElidedClickableLabel, self).minimumSizeHint().height())

    def sizeHint(self):
        # Ideally request full width
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(self._full_text) if hasattr(fm, "horizontalAdvance") else fm.width(self._full_text)
        return QtCore.QSize(w, super(ElidedClickableLabel, self).sizeHint().height())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        metrics = painter.fontMetrics()
        
        # Elide from left as requested
        elided = metrics.elidedText(self._full_text, QtCore.Qt.ElideLeft, self.width())
        
        # Draw styling for link-like appearance
        if self.underMouse():
             painter.setPen(QtGui.QColor("#7aa3ba")) # lighter blue hover
        else:
             painter.setPen(QtGui.QColor("#5285a6")) # standard link blue

        painter.drawText(self.rect(), self.alignment() | QtCore.Qt.AlignVCenter, elided)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()


class TagFlowWidget(QtWidgets.QWidget):
    """Widget wrapper for FlowLayout to handle height-for-width correctly."""
    def __init__(self, parent=None):
        super(TagFlowWidget, self).__init__(parent)
        self.setLayout(FlowLayout(margin=0, hSpacing=4, vSpacing=4))
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)

    def add_tag(self, text, callback):
        btn = QtWidgets.QPushButton(str(text))
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.setFixedHeight(22)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                border: 1px solid #555;
                border-radius: 10px;
                color: #eee;
                padding: 0px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #555;
                color: #fff;
                border-color: #666;
            }
            QPushButton:pressed {
                background-color: #222;
            }
        """)
        btn.clicked.connect(callback)
        self.layout().addWidget(btn)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.layout().heightForWidth(width)

    def sizeHint(self):
        # Provide a default reasonable size hint logic
        w = self.width() if self.width() > 0 else 300
        h = self.layout().heightForWidth(w)
        return QtCore.QSize(w, h)
        
    def resizeEvent(self, event):
        # Critical: Inform parent layout that our height might have changed due to new width
        self.updateGeometry()
        super(TagFlowWidget, self).resizeEvent(event)


# -------------------- Info Dialog --------------------


class InfoDialog(QtWidgets.QDialog):
    filterRequested = QtCore.Signal(str, str)
    editRequested = QtCore.Signal()

    def __init__(self, name, data, parent=None):
        super(InfoDialog, self).__init__(parent)
        self.setWindowTitle(name)
        self.setMinimumHeight(450)
        self.resize(350, 500)
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

        # 1. Tags (List) -> TagFlowWidget
        if filter_cat == "Tags" and isinstance(value, list):
            if not value:
                lbl = QtWidgets.QLabel("Empty")
                lbl.setStyleSheet("color: #888; font-style: italic;")
                self.form_layout.addRow(label + ":", lbl)
                return

            container = TagFlowWidget()
            for tag in value:
                # Capture tag for lambda
                callback = lambda checked=False, t=tag: self._emit_filter("Tags", t)
                container.add_tag(tag, callback)
            
            self.form_layout.addRow(label + ":", container)
            return

        # 2. Path or Link -> ElidedClickableLabel
        if (is_link or is_path) and value != "Empty":
            elided_lbl = ElidedClickableLabel(value)
            heading_lbl = QtWidgets.QLabel(label + ":")
            
            if is_link:
                href = value if value.startswith("http") else "http://" + value
                elided_lbl.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(href)))
            elif is_path:
                elided_lbl.clicked.connect(lambda: self._open_folder(value))
                
            self.form_layout.addRow(heading_lbl, elided_lbl)
            return

        # 3. Standard Text / Filter Links (Collection/Author)
        lbl = QtWidgets.QLabel()
        lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        lbl.setWordWrap(True)

        if filter_cat:
            # Collection/Author
            disp = value or "Empty"
            filt = value or "Empty"
            if disp == "Empty":
                disp = "<i>Empty</i>"

            lbl.setText(self._filter_tmpl % (filt, disp))
            lbl.linkActivated.connect(lambda v: self._emit_filter(filter_cat, v))
        else:
            if value == "Empty":
                lbl.setText("<i>Empty</i>")
                lbl.setStyleSheet("color: #888;")
            else:
                lbl.setText(str(value))
            lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        self.form_layout.addRow(label + ":", lbl)

    def _emit_filter(self, cat, val):
        self.filterRequested.emit(cat, val)
        self.accept()

    def _on_edit(self):
        self.editRequested.emit()

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



class TagEditor(QtWidgets.QWidget):
    """Widget for editing tags with visual pills."""

    def __init__(self, tags=None, parent=None):
        super(TagEditor, self).__init__(parent)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.all_tags = sorted(list(tags)) if tags else []
        self.current_tags = []

        self.setLayout(FlowLayout(margin=0, hSpacing=4, vSpacing=4))

        # Input Field
        self.input_line = QtWidgets.QLineEdit()
        self.input_line.setPlaceholderText("Add tag...")
        self.input_line.setFixedHeight(22)
        self.input_line.setStyleSheet("background: transparent; border: none; color: #eee;")
        self.input_line.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        
        self.input_line.textChanged.connect(self._update_input_width)
        self.input_line.returnPressed.connect(self._on_return_pressed)
        self.input_line.installEventFilter(self)

        # Completer
        if self.all_tags:
            self.completer = QtWidgets.QCompleter(self.all_tags, self)
            self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.completer.setFilterMode(QtCore.Qt.MatchContains)
            self.completer.activated.connect(self._on_completer_activated)
            self.input_line.setCompleter(self.completer)
            
        self._refresh_ui()
        self._update_input_width()

    def _update_input_width(self, text=None):
        if text is None:
            text = self.input_line.text()
            
        fm = self.input_line.fontMetrics()
        
        def get_width(t):
            if hasattr(fm, "horizontalAdvance"):
                return fm.horizontalAdvance(t)
            return fm.width(t)

        w_text = get_width(text)
        w_place = get_width(self.input_line.placeholderText())
        
        # Ensure it fits "Add tag..." or current text, plus padding
        width = max(w_text, w_place) + 20
        self.input_line.setFixedWidth(width)

    def eventFilter(self, source, event):
        if source == self.input_line and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Backspace and not self.input_line.text():
                if self.current_tags:
                    self.remove_tag(self.current_tags[-1])
                    return True
        return super(TagEditor, self).eventFilter(source, event)

    def _on_completer_activated(self, text):
        if text:
            self.add_tag(text)

    def _on_return_pressed(self):
        text = self.input_line.text().strip()
        if not text:
            return

        parts = [t.strip() for t in text.split(",") if t.strip()]
        for part in parts:
            self.add_tag(part)

    def add_tag(self, text):
        if not text:
            return
            
        # Case-insensitive check
        if any(t.lower() == text.lower() for t in self.current_tags):
            return

        self.current_tags.append(text)
        self._refresh_ui()

        # Defer clearing to handle QCompleter's default behavior which might restore text
        QtCore.QTimer.singleShot(0, self._post_add_cleanup)

    def _post_add_cleanup(self):
        self.input_line.clear()
        self.input_line.setFocus()

    def remove_tag(self, text):
        if text in self.current_tags:
            self.current_tags.remove(text)
            self._refresh_ui()

    def _create_pill_widget(self, text):
        pill = QtWidgets.QFrame()
        pill.setObjectName("TagPill")
        pill.setFixedHeight(22)
        pill.setStyleSheet("""
            #TagPill {
                background-color: #444;
                border: 1px solid #555;
                border-radius: 10px;
            }
        """)

        layout = QtWidgets.QHBoxLayout(pill)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        label = QtWidgets.QLabel(text)
        label.setStyleSheet("background: transparent; border: none; color: #eee; font-size: 11px;")
        layout.addWidget(label)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                color: #aaa;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #666;
                color: #fff;
            }
        """)
        # Using default arg to capture 'text' value correctly in loop/scope
        close_btn.clicked.connect(lambda checked=False, t=text: self.remove_tag(t))
        layout.addWidget(close_btn)
        
        return pill

    def _refresh_ui(self):
        layout = self.layout()
        
        # Remove all items safely
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w and w != self.input_line:
                w.deleteLater()
            
        # Add pills
        for tag in self.current_tags:
            pill = self._create_pill_widget(tag)
            layout.addWidget(pill)
            pill.show()
            
        # Add input line
        layout.addWidget(self.input_line)
        self.input_line.show()

    def getTags(self):
        return list(self.current_tags)

    def setTags(self, tags):
        self.current_tags = list(tags) if tags else []
        self._refresh_ui()

    def setPlaceholderText(self, text):
        self.input_line.setPlaceholderText(text)



# -------------------- Batch Add / Scanner --------------------


class ScannerWorker(QtCore.QThread):
    """Background thread to scan for Maya files and categorize them."""

    fileDiscovered = QtCore.Signal(str, str)  # path, category: 'new', 'exists', 'blacklisted'
    finished = QtCore.Signal()

    def __init__(self, directory, existing_paths, blacklist, parent=None):
        super(ScannerWorker, self).__init__(parent)
        self.directory = directory
        self.existing_paths = existing_paths  # Set of normalized paths
        self.blacklist = blacklist  # Set/List of normalized paths
        self._is_running = True

    def run(self):
        for root, dirs, files in os.walk(self.directory):
            if not self._is_running:
                break

            # Skip common hidden/system/cache folders
            dirs[:] = [
                d for d in dirs if not (d.startswith(".") or d.endswith(".anim") or d == "__pycache__")
            ]

            for f in files:
                if not self._is_running:
                    break
                if f.lower().endswith((".ma", ".mb")):
                    path = os.path.normpath(os.path.join(root, f))
                    # Check against sets using normalized path
                    lookup_path = path if sys.platform != "win32" else path.lower()
                    if lookup_path in self.blacklist:
                        self.fileDiscovered.emit(path, "blacklisted")
                    elif lookup_path in self.existing_paths:
                        self.fileDiscovered.emit(path, "exists")
                    else:
                        self.fileDiscovered.emit(path, "new")
        self.finished.emit()

    def stop(self):
        self._is_running = False


class ScannerItemWidget(QtWidgets.QWidget):
    """Horizontal widget for a discovered file in the scanner list."""

    editRequested = QtCore.Signal(str)
    blacklistRequested = QtCore.Signal(str)
    whitelistRequested = QtCore.Signal(str)

    def __init__(self, path, category, parent=None):
        super(ScannerItemWidget, self).__init__(parent)
        self.path = path
        self.category = category  # 'new', 'exists', 'blacklisted'

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)

        # Path Label (Elided)
        self.path_lbl = QtWidgets.QLabel(path)
        self.path_lbl.setToolTip(path)
        self.path_lbl.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self._is_added = False
        layout.addWidget(self.path_lbl, 1)

        # Buttons
        self.btn_layout = QtWidgets.QHBoxLayout()
        self.btn_layout.setSpacing(4)
        layout.addLayout(self.btn_layout)

        self.edit_btn = QtWidgets.QPushButton()
        if category == "new":
            self.edit_btn.setToolTip("Configure and add/update this rig")
            self.edit_btn.setFixedSize(22, 22)
        else:
            self.edit_btn.setIcon(utils.get_icon("edit.svg"))
            self.edit_btn.setToolTip("Configure and add/update this rig")
            self.edit_btn.setFixedSize(22, 22)
        self.edit_btn.clicked.connect(lambda: self.editRequested.emit(self.path))
        self.btn_layout.addWidget(self.edit_btn)

        if category == "blacklisted":
            self.whitelist_btn = QtWidgets.QPushButton()
            self.whitelist_btn.setIcon(utils.get_icon("whitelist.svg"))
            # self.whitelist_btn.setText("Whitelist")
            self.whitelist_btn.setToolTip("Remove from blacklist")
            self.whitelist_btn.setFixedSize(22, 22)
            self.whitelist_btn.clicked.connect(lambda: self.whitelistRequested.emit(self.path))
            self.btn_layout.addWidget(self.whitelist_btn)
            self.edit_btn.setVisible(False)
        else:
            self.blacklist_btn = QtWidgets.QPushButton()
            self.blacklist_btn.setIcon(utils.get_icon("blacklist.svg"))
            self.blacklist_btn.setToolTip("Don't show this file again")
            self.blacklist_btn.setFixedSize(22, 22)
            self.blacklist_btn.clicked.connect(lambda: self.blacklistRequested.emit(self.path))
            self.btn_layout.addWidget(self.blacklist_btn)

            if category == "exists":
                self.path_lbl.setStyleSheet("QLabel { color: #aaa;}")

    def paintEvent(self, event):
        """Update elided text on the path label manually to ensure it fits with two-tone colors."""
        super(ScannerItemWidget, self).paintEvent(event)
        width = self.path_lbl.width()
        if width <= 0:
            return

        metrics = QtGui.QFontMetrics(self.path_lbl.font())
        elided = metrics.elidedText(self.path, QtCore.Qt.ElideLeft, width)

        # Base colors
        dir_color = "gray"
        file_color = "#eee"

        # State-based color overrides
        if self._is_added:
            dir_color = "gray"
            file_color = "#7cb380"  # Soft green
        elif self.category == "exists":
            dir_color = "gray"
            file_color = "#aaa"
        elif self.category == "blacklisted":
            dir_color = "gray"
            file_color = "#aaa"

        # Split elided text into directory and filename
        idx = max(elided.rfind("/"), elided.rfind("\\"))
        if idx != -1:
            dir_part = elided[: idx + 1]
            file_part = elided[idx + 1 :]

            # Apply bold if added
            if self._is_added:
                file_part = "<b>{}</b>".format(file_part)

            rich_text = "<span style='color: {};'>{}</span><span style='color: {};'>{}</span>".format(
                dir_color, dir_part, file_color, file_part
            )
        else:
            rich_text = "<span style='color: {};'>{}</span>".format(file_color, elided)

        # Update if changed
        if getattr(self, "_last_rich_text", "") != rich_text:
            self._last_rich_text = rich_text
            self.path_lbl.setText(rich_text)

    def set_added(self):
        """Update visual state when rig is added to DB."""
        self._is_added = True
        self.edit_btn.setText("Edit")
        # styleSheet still sets basic props, paintEvent handles colors/bold
        self.path_lbl.setStyleSheet("font-weight: bold;")
        self._last_rich_text = ""  # Force refresh
        self.update()

    def set_category(self, category):
        """Switch the category and update UI buttons/styles."""
        self.category = category

        # Cleanup existing dynamic buttons
        if hasattr(self, "blacklist_btn"):
            self.blacklist_btn.setParent(None)
            self.blacklist_btn.deleteLater()
            del self.blacklist_btn
        if hasattr(self, "whitelist_btn"):
            self.whitelist_btn.setParent(None)
            self.whitelist_btn.deleteLater()
            del self.whitelist_btn

        self.edit_btn.setText("Add" if category == "new" else "Edit")
        self.edit_btn.setVisible(category != "blacklisted")

        if category == "blacklisted":
            self.whitelist_btn = QtWidgets.QPushButton()
            self.whitelist_btn.setText("Whitelist")
            self.whitelist_btn.setToolTip("Remove from blacklist")
            self.whitelist_btn.setFixedSize(65, 22)
            self.whitelist_btn.clicked.connect(lambda: self.whitelistRequested.emit(self.path))
            self.btn_layout.addWidget(self.whitelist_btn)
        else:
            self.blacklist_btn = QtWidgets.QPushButton()
            self.blacklist_btn.setText("Blacklist")
            self.blacklist_btn.setToolTip("Don't show this file again")
            self.blacklist_btn.setFixedSize(65, 22)
            self.blacklist_btn.clicked.connect(lambda: self.blacklistRequested.emit(self.path))
            self.btn_layout.addWidget(self.blacklist_btn)


class CollapsibleSection(QtWidgets.QWidget):
    """A section that can be toggled to show/hide its scrolled content."""

    def __init__(self, title, parent=None):
        super(CollapsibleSection, self).__init__(parent)
        self._items = []
        self._title = title

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.btn = QtWidgets.QPushButton(title)
        self.btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn.setCheckable(True)
        self.btn.setChecked(False)
        self.btn.setStyleSheet(
            "QPushButton { text-align: left; font-weight: bold; background: #333; padding: 6px; border: none; border-radius: 3px; }"
            "QPushButton:hover { background: #3a3a3a; }"
            "QPushButton:checked { background: #3a3a3a; }"
        )
        self.btn.toggled.connect(self._toggle)

        # Scroll Area for content
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setVisible(False)
        self.scroll.setStyleSheet("QScrollArea { border: 1px solid #333; border-top: none; }")

        self.container = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(2)

        self.empty_lbl = QtWidgets.QLabel("No items")
        self.empty_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("color: #888; font-style: italic; margin: 10px;")
        self.empty_lbl.setVisible(True)  # Visible by default since items is empty
        self.content_layout.addWidget(self.empty_lbl)

        self.content_layout.addStretch()
        self.scroll.setWidget(self.container)

        layout.addWidget(self.btn)
        layout.addWidget(self.scroll)

        self.update_title()

    def set_empty_text(self, text):
        self.empty_lbl.setText(text)

    def _toggle(self, checked):
        self.scroll.setVisible(checked)
        self.update_title()

        if checked:
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        else:
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)

        if self.parentWidget() and self.parentWidget().layout():
            ly = self.parentWidget().layout()
            if hasattr(ly, "setStretchFactor"):
                ly.setStretchFactor(self, 1 if checked else 0)

    def addWidget(self, widget):
        self._items.append(widget)
        self.empty_lbl.setVisible(False)

        self.content_layout.insertWidget(self.content_layout.count() - 1, widget)
        self.update_title()

    def removeWidget(self, widget):
        if widget in self._items:
            self._items.remove(widget)
            self.content_layout.removeWidget(widget)
            widget.setParent(None)

            if not self._items:
                self.empty_lbl.setVisible(True)

            self.update_title()

    def update_title(self):
        self.btn.setText(f"{self._title} ({len(self._items)})")


class GeminiWorker(QtCore.QThread):
    """Background thread to query Gemini API for rig tags."""

    finished = QtCore.Signal(dict)  # Returns dict of {filename: metadata}

    def __init__(self, api_key, file_paths, parent=None):
        super(GeminiWorker, self).__init__(parent)
        self.api_key = api_key
        self.file_paths = file_paths

    def run(self):
        try:
            # We assume utils.query_gemini is available and blocking
            json_str = utils.query_gemini(self.api_key, self.file_paths)
            if json_str:
                data = json.loads(json_str)
                self.finished.emit(data)
            else:
                self.finished.emit({})
        except Exception as e:
            utils.LOG.error(f"Gemini Worker Error: {e}")
            self.finished.emit({})


class ResponsiveScrollArea(QtWidgets.QScrollArea):
    """ScrollArea that adjusts its height to fit its content."""

    def __init__(self, parent=None):
        super(ResponsiveScrollArea, self).__init__(parent)
        self.setWidgetResizable(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)

    def eventFilter(self, o, e):
        if o == self.widget() and e.type() == QtCore.QEvent.LayoutRequest:
            self.updateGeometry()
        return super(ResponsiveScrollArea, self).eventFilter(o, e)

    def setWidget(self, widget):
        super(ResponsiveScrollArea, self).setWidget(widget)
        if widget:
            widget.installEventFilter(self)

    def sizeHint(self):
        if self.widget():
            h = self.widget().sizeHint().height()
            f = self.frameWidth() * 2
            return QtCore.QSize(super(ResponsiveScrollArea, self).sizeHint().width(), h + f)
        return super(ResponsiveScrollArea, self).sizeHint()


class ReplacementListWidget(QtWidgets.QListWidget):
    """List widget that supports drag-and-drop reordering."""
    orderChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super(ReplacementListWidget, self).__init__(parent)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(2)
        self.setMouseTracking(True)
        # Verify drag is enabled
        self.setDragEnabled(True)
        self.setAcceptDrops(True)

    def dropEvent(self, event):
        super(ReplacementListWidget, self).dropEvent(event)
        self.orderChanged.emit()


class ManageRigsDialog(QtWidgets.QDialog):
    """Dialog for scanning, batch-adding, and managing rigs/settings."""

    rigAdded = QtCore.Signal(str, dict)
    blacklistChanged = QtCore.Signal(list)

    def __init__(
        self,
        directory=None,
        rig_data=None,
        blacklist=None,
        collections=None,
        authors=None,
        tags=None,
        initial_tab=0,
        parent=None,
    ):
        super(ManageRigsDialog, self).__init__(parent)
        self.setWindowTitle("Manage Rigs")
        self.resize(800, 600)

        self.initial_tab = initial_tab
        self.directory = directory
        self.rig_data = rig_data or {}
        self.blacklist = list(blacklist) if blacklist else []
        self.collections = collections or []
        self.authors = authors or []
        self.tags = tags or []

        # Settings
        self.settings = QtCore.QSettings("LibraryUI", "RigManager")

        self.existing_paths = {}  # Normalized lookup -- name
        self.alternative_paths = set()  # Normalized lookup set
        for name, d in rig_data.items():
            if name.startswith("_"):
                continue

            # Map main path
            main_p = d.get("path")
            if main_p:
                norm_p = os.path.normpath(main_p)
                lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()
                self.existing_paths[lookup_p] = name

            # Map alternatives
            for alt in d.get("alternatives", []):
                if not alt:
                    continue
                norm_p = os.path.normpath(alt)
                lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()
                self.existing_paths[lookup_p] = name
                self.alternative_paths.add(lookup_p)

        self._widgets_map = {}  # original path -- widget

        self._build_ui()
        if self.directory:
            self._start_scan()
        else:
            self._populate_existing()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        # --- Tab 1: Rigs ---
        self.tab_rigs = QtWidgets.QWidget()
        rigs_layout = QtWidgets.QVBoxLayout(self.tab_rigs)

        self.lbl_scan_info = QtWidgets.QLabel(f"Scanning: <i>{self.directory}</i>" if self.directory else "")
        self.lbl_scan_info.setVisible(bool(self.directory))
        rigs_layout.addWidget(self.lbl_scan_info)

        # New Rigs Section
        self.sec_new = CollapsibleSection("Discovered New Rigs")
        self.sec_new.set_empty_text("Searching for rigs...")
        self.sec_new.setVisible(bool(self.directory))
        rigs_layout.addWidget(self.sec_new)
        self.sec_new.btn.setChecked(True)  # Expand by default

        # AI Button
        self.ai_btn = QtWidgets.QPushButton("Auto-Tag New Rigs with Gemini AI")
        self.ai_btn.clicked.connect(self._run_gemini)
        # Always hidden initially until items are found or if not in scan mode
        self.ai_btn.setVisible(False)
        rigs_layout.addWidget(self.ai_btn)

        # Existing Rigs Section
        self.sec_exists = CollapsibleSection("In Database")
        self.sec_exists.set_empty_text(
            "No rigs in database." if not self.directory else "No existing rigs found in this folder."
        )
        # If managing (no dir), expand by default
        # If managing (no dir), expand by default
        rigs_layout.addWidget(self.sec_exists)
        if not self.directory:
            self.sec_exists.btn.setChecked(True)

        # Blacklisted Section
        self.sec_black = CollapsibleSection("Blacklisted")
        self.sec_black.set_empty_text("No blacklisted files.")
        rigs_layout.addWidget(self.sec_black)

        rigs_layout.addStretch()

        self.tabs.addTab(self.tab_rigs, "Rigs")

        # --- Tab 2: Settings ---
        self.tab_settings = QtWidgets.QWidget()
        self._build_settings_tab()
        self.tabs.addTab(self.tab_settings, "Settings")

        # Set initial tab
        self.tabs.setCurrentIndex(self.initial_tab)

        # --- Main Footer ---
        footer = QtWidgets.QHBoxLayout()
        # footer.setContentsMargins(10, 0, 10, 10) # Optional spacing

        btn_scan = QtWidgets.QPushButton("Scan Folder")
        btn_scan.setIcon(utils.get_icon("search.svg"))
        btn_scan.clicked.connect(self._trigger_scan_folder)

        btn_add = QtWidgets.QPushButton("Add Manually")
        btn_add.setIcon(utils.get_icon("add.svg"))
        btn_add.clicked.connect(self._trigger_add_manual)

        self.done_btn = QtWidgets.QPushButton("Done")
        self.done_btn.clicked.connect(self.accept)

        footer.addWidget(btn_scan)
        footer.addWidget(btn_add)
        footer.addStretch()
        footer.addWidget(self.done_btn)

        layout.addLayout(footer)

    def _build_settings_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_settings)

        # Gemini API Key
        grp_ai = QtWidgets.QGroupBox("Gemini AI Integration")
        lay_ai = QtWidgets.QVBoxLayout(grp_ai)

        lay_key = QtWidgets.QHBoxLayout()
        lay_key.addWidget(QtWidgets.QLabel("API Key:"))
        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_input.setText(self.settings.value("gemini_api_key", ""))
        self.api_key_input.textChanged.connect(lambda txt: self.settings.setValue("gemini_api_key", txt))
        lay_key.addWidget(self.api_key_input)
        lay_ai.addLayout(lay_key)

        lbl_info = QtWidgets.QLabel(
            "<span style='font-size: 7.5pt;'>Get your API key from: <a href='https://aistudio.google.com/api-keys'>Google AI Studio</a></span>"
        )
        lbl_info.setOpenExternalLinks(True)
        lay_ai.addWidget(lbl_info)

        layout.addWidget(grp_ai)

        # Path Replacements
        grp_paths = QtWidgets.QGroupBox("Path Replacements (Local)")
        lay_paths = QtWidgets.QVBoxLayout(grp_paths)
        lay_paths.setSpacing(5)

        # Header
        head_lay = QtWidgets.QHBoxLayout()
        head_lay.addWidget(QtWidgets.QLabel("Find Path:"))
        head_lay.addWidget(QtWidgets.QLabel("Replace With:"))
        head_lay.addSpacing(30)  # For delete button
        lay_paths.addLayout(head_lay)

        # List for replacements (Draggable)
        self.replacements_list = ReplacementListWidget()
        self.replacements_list.setStyleSheet(
            "QListWidget { background: transparent; border: 1px solid #444; border-radius: 4px; }"
            "QListWidget::item { border-bottom: 1px solid #333; }"
        )
        self.replacements_list.orderChanged.connect(self._save_path_replacements_from_ui)
        lay_paths.addWidget(self.replacements_list)

        # Add Button
        lay_add = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add Replacement")
        add_btn.setIcon(utils.get_icon("add.svg"))
        add_btn.setStyleSheet("font-weight: bold;")
        add_btn.clicked.connect(lambda: self._add_replacement_row("", ""))
        lay_add.addWidget(add_btn)
        lay_add.addStretch()
        lay_paths.addLayout(lay_add)

        layout.addWidget(grp_paths)
        layout.addStretch()

        # Load and populate
        self._load_replacements_ui()

    def _load_replacements_ui(self):
        self.replacements_list.clear()

        raw = self.settings.value("path_replacements", "[]")
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []

        for find_txt, rep_txt in data:
            self._add_replacement_row(find_txt, rep_txt)

    def _add_replacement_row(self, find_val, rep_val):
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(QtCore.QSize(0, 42))  # Fixed height for row

        row_widget = QtWidgets.QWidget()
        row_lay = QtWidgets.QHBoxLayout(row_widget)
        row_lay.setContentsMargins(5, 5, 5, 5)
        row_lay.setSpacing(8)

        # Handle
        handle_lbl = QtWidgets.QLabel("☰")  # Unicode trigram for handle
        handle_lbl.setStyleSheet("color: #666; font-size: 16px; font-weight: bold;")
        handle_lbl.setCursor(QtCore.Qt.OpenHandCursor)
        handle_lbl.setMouseTracking(True)
        handle_lbl.setFixedWidth(20)
        handle_lbl.setAlignment(QtCore.Qt.AlignCenter)
        handle_lbl.setToolTip("Drag to reorder")
        row_lay.addWidget(handle_lbl)

        input_find = QtWidgets.QLineEdit(find_val)
        input_find.setPlaceholderText("e.g. D:/Rigs")

        input_rep = QtWidgets.QLineEdit(rep_val)
        input_rep.setPlaceholderText("e.g. Z:/Rigs")

        # Auto-save changes
        input_find.textChanged.connect(self._save_path_replacements_from_ui)
        input_rep.textChanged.connect(self._save_path_replacements_from_ui)

        del_btn = QtWidgets.QPushButton()
        del_btn.setIcon(utils.get_icon("trash.svg"))
        del_btn.setFixedSize(20, 20)
        del_btn.setToolTip("Remove this replacement")
        del_btn.clicked.connect(lambda: self._remove_replacement_row(item))

        row_lay.addWidget(input_find)

        arrow_lbl = QtWidgets.QLabel()
        arrow_lbl.setPixmap(utils.get_icon("right_arrow.svg").pixmap(16, 16))
        row_lay.addWidget(arrow_lbl)

        row_lay.addWidget(input_rep)
        row_lay.addWidget(del_btn)

        self.replacements_list.addItem(item)
        self.replacements_list.setItemWidget(item, row_widget)

        # Ensure save is called if this is a new empty row adding
        if not find_val and not rep_val:
            self._save_path_replacements_from_ui()

    def _remove_replacement_row(self, item):
        row = self.replacements_list.row(item)
        self.replacements_list.takeItem(row)
        # Schedule save
        QtCore.QTimer.singleShot(10, self._save_path_replacements_from_ui)

    def _save_path_replacements_from_ui(self):
        data = []
        for i in range(self.replacements_list.count()):
            item = self.replacements_list.item(i)
            wid = self.replacements_list.itemWidget(item)
            if wid:
                # Layout logic: [Handle, InputFind, Arrow, InputRep, DelBtn]
                # indices: 0=Handle, 1=InputFind, 2=Arrow, 3=InputRep, 4=DelBtn
                layout = wid.layout()
                if layout and layout.count() >= 5:
                    find_edit = layout.itemAt(1).widget()
                    rep_edit = layout.itemAt(3).widget()

                    if isinstance(find_edit, QtWidgets.QLineEdit) and isinstance(
                        rep_edit, QtWidgets.QLineEdit
                    ):
                        f_txt = self.normpath_posix_keep_trailing(find_edit.text())
                        r_txt = self.normpath_posix_keep_trailing(rep_edit.text())
                        # Only save if at least find_txt has something
                        if f_txt or r_txt:
                            data.append([f_txt, r_txt])

        json_str = json.dumps(data)
        self.settings.setValue("path_replacements", json_str)

    @staticmethod
    def normpath_posix_keep_trailing(path):
        has_trailing = path.endswith(("/", "\\"))
        norm = os.path.normpath(path).replace("\\", "/")
        if has_trailing and not norm.endswith("/"):
            norm += "/"
        return norm

    def _populate_existing(self):
        # Populate sec_exists and sec_black from full database since no directory scan
        self.sec_exists.set_empty_text("Database is empty.")

        # We can iterate rig_data
        for name, data in self.rig_data.items():
            path = data.get("path", "")
            if path:
                item = ScannerItemWidget(path, "exists")
                item.editRequested.connect(self._on_edit_request)
                item.blacklistRequested.connect(self._on_blacklist_request)
                self.sec_exists.addWidget(item)
                self._widgets_map[path] = item

        for path in self.blacklist:
            self.sec_black.addWidget(item)
            self._widgets_map[path] = item

    def _clear_lists(self):
        """Clears all items from the lists."""
        for section in [self.sec_new, self.sec_exists, self.sec_black]:
            if not section:
                continue
            while section._items:
                section.removeWidget(section._items[0])
        self._widgets_map.clear()

    def _trigger_scan_folder(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory to Scan")
        if not directory:
            return

        self.directory = os.path.normpath(directory)
        self.lbl_scan_info.setText(f"Scanning: <i>{self.directory}</i>")
        self.lbl_scan_info.setVisible(True)

        # Clear lists to switch context
        self._clear_lists()

        # Reset UI for scan
        self.sec_new.setVisible(True)
        # Clear items in sec_new
        while self.sec_new._items:
            w = self.sec_new._items[0]
            self.sec_new.removeWidget(w)

        self.sec_new.set_empty_text("Scanning...")
        self.sec_new.btn.setChecked(True)

        self.ai_btn.setVisible(False)
        self._start_scan()

    def _trigger_add_manual(self):
        file_filter = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Rig File", "", file_filter)
        if not path:
            return

        path = os.path.normpath(path)

        # Check duplicates
        for name, data in self.rig_data.items():
            if name.startswith("_"):
                continue
            all_paths = [data.get("path", "")] + data.get("alternatives", [])
            norm_paths = [os.path.normpath(p) for p in all_paths if p]
            if path in norm_paths:
                # Found duplicate in database
                # Find matching widget for this path
                existing_item = self._widgets_map.get(
                    os.path.normpath(path) if sys.platform != "win32" else os.path.normpath(path).lower()
                )

                # If not found by direct path, maybe check main path if it was an alt?
                if not existing_item:
                    main_p = data.get("path")
                    if main_p:
                        norm_main = os.path.normpath(main_p)
                        lookup = norm_main if sys.platform != "win32" else norm_main.lower()
                        existing_item = self._widgets_map.get(lookup)

                QtWidgets.QMessageBox.warning(
                    self,
                    "Duplicate Found",
                    "The rig '{}' ({}) is already in the database.".format(
                        name, getattr(utils, "truncate_path", lambda p: p)(path)
                    ),
                )

                if existing_item:
                    # Highlight existing
                    self.sec_exists.btn.setChecked(True)
                    self.sec_exists.scroll.ensureWidgetVisible(existing_item)

                    orig_style = existing_item.styleSheet()
                    # Flashing style
                    existing_item.setStyleSheet("background-color: #554444; border: 1px solid #DD5555;")
                    QtCore.QTimer.singleShot(1000, lambda: existing_item.setStyleSheet(orig_style))

                return

        dlg = RigSetupDialog(
            existing_names=list(self.rig_data.keys()),
            collections=self.collections,
            authors=self.authors,
            tags=self.tags,
            mode="add",
            file_path=path,
            parent=self,
        )

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            res = dlg.result_data
            if res:
                self.rigAdded.emit(res["name"], res["data"])
                self.rig_data[res["name"]] = res["data"]
                # self.existing_paths[path] = res["name"] # Should update local map too

                # Add to existing list directly
                item = ScannerItemWidget(path, "exists")
                item.set_added()  # Visual trick to show it's fresh?
                item.editRequested.connect(self._on_edit_request)
                item.blacklistRequested.connect(self._on_blacklist_request)
                self.sec_exists.addWidget(item)
                self._widgets_map[path] = item

    def _run_gemini(self):
        api_key = self.settings.value("gemini_api_key", "")
        if not api_key:
            QtWidgets.QMessageBox.warning(self, "No API Key", "Please set Gemini API Key in Settings tab.")
            return

        # Gather new paths
        new_paths = []
        for widget in self.sec_new._items:
            if isinstance(widget, ScannerItemWidget):
                new_paths.append(widget.path)

        if not new_paths:
            return

        self.ai_btn.setEnabled(False)
        self.ai_btn.setText("Processing with Gemini...")

        self.gemini_worker = GeminiWorker(api_key, new_paths, self)
        self.gemini_worker.finished.connect(self._on_gemini_finished)
        self.gemini_worker.start()

    def _on_gemini_finished(self, results):
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("Auto-Tag New Rigs with Gemini AI")

        if not results:
            QtWidgets.QMessageBox.warning(self, "Gemini Error", "Failed to process rigs or empty result.")
            return

        # Results is dict: { "CharacterName": { "path": ..., "tags": ... } }
        # The result keys are character names.

        count = 0
        for char_name, data in results.items():
            path = data.get("path")
            if not path:
                continue

            norm_p = os.path.normpath(path)
            matching_widget = None
            for p, wid in self._widgets_map.items():
                if os.path.normpath(p) == norm_p:
                    matching_widget = wid
                    break

            if matching_widget:
                # Automate "Add"
                # We Simulate the result data structure expected by rigAdded
                res_data = {
                    "path": path,
                    "image": "",  # Gemini returns null
                    "tags": data.get("tags", []),
                    "collection": data.get("collection") or "Empty",
                    "author": data.get("author") or "Empty",
                    "link": data.get("link") or "Empty",
                }

                # Emit signal to Main UI to add to DB
                self.rigAdded.emit(char_name, res_data)

                # Update UI
                matching_widget.set_added()

                # Update internal data so we don't re-add
                self.rig_data[char_name] = res_data
                self.existing_paths[norm_p] = char_name

                count += 1

        QtWidgets.QMessageBox.information(self, "Gemini Batch", f"Successfully auto-added {count} rigs.")

    def _start_scan(self):
        # Create normalized sets for fast, case-consistent lookup
        lookup_existing = set(self.existing_paths.keys())
        lookup_blacklist = set()
        for p in self.blacklist:
            norm_p = os.path.normpath(p)
            lookup_blacklist.add(norm_p if sys.platform != "win32" else norm_p.lower())

        self.worker = ScannerWorker(self.directory, lookup_existing, lookup_blacklist, self)
        self.worker.fileDiscovered.connect(self._on_file_discovered)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.start()

    def _on_scan_finished(self):
        """Update status label if nothing was found."""
        if hasattr(self, "sec_new"):
            if not self.sec_new._items:
                self.sec_new.set_empty_text("No new rigs found in this directory.")
                if hasattr(self, "ai_btn"):
                    self.ai_btn.setVisible(False)
            else:
                if hasattr(self, "ai_btn"):
                    self.ai_btn.setVisible(True)

    def _on_file_discovered(self, path, category):
        # if category == "new":
        #    self._status_lbl.setVisible(False)

        item = ScannerItemWidget(path, category)

        # Disable edit if it's an alternative
        if category == "exists":
            norm_p = os.path.normpath(path)
            lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()
            if lookup_p in self.alternative_paths:
                item.edit_btn.setEnabled(False)
                item.edit_btn.setToolTip(
                    "Path exists as an alternative file for rig: '{}'".format(self.existing_paths[lookup_p])
                )

        item.editRequested.connect(self._on_edit_request)
        item.blacklistRequested.connect(self._on_blacklist_request)
        item.whitelistRequested.connect(self._on_whitelist_request)

        self._widgets_map[path] = item

        if category == "new":
            self.sec_new.addWidget(item)
        elif category == "exists":
            self.sec_exists.addWidget(item)
        elif category == "blacklisted":
            self.sec_black.addWidget(item)

    def _on_edit_request(self, path):
        rig_name = self.existing_paths.get(path)
        mode = "edit" if rig_name else "add"
        rig_data = self.rig_data.get(rig_name) if rig_name else None

        dlg = RigSetupDialog(
            existing_names=list(self.rig_data.keys()),
            collections=self.collections,
            authors=self.authors,
            tags=self.tags,
            mode=mode,
            file_path=path,
            rig_name=rig_name,
            rig_data=rig_data,
            parent=self,
        )

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            res = dlg.result_data
            if res:
                self.rigAdded.emit(res["name"], res["data"])
                self.rig_data[res["name"]] = res["data"]
                self.existing_paths[path] = res["name"]

                item = self._widgets_map.get(path)
                if item:
                    item.set_added()

    def _on_blacklist_request(self, path):
        norm_path = os.path.normpath(path)
        if norm_path not in self.blacklist:
            self.blacklist.append(norm_path)
            self.blacklistChanged.emit(self.blacklist)

            item = self._widgets_map.get(path)
            if item:
                # Move to blacklist section
                if item.category == "new":
                    self.sec_new.removeWidget(item)
                elif item.category == "exists":
                    self.sec_exists.removeWidget(item)

                item.set_category("blacklisted")
                self.sec_black.addWidget(item)

    def _on_whitelist_request(self, path):
        norm_path = os.path.normpath(path)
        if norm_path in self.blacklist:
            self.blacklist.remove(norm_path)
            self.blacklistChanged.emit(self.blacklist)

            item = self._widgets_map.get(path)
            if item:
                self.sec_black.removeWidget(item)

                # Determine where it should go back
                lookup_p = norm_path if sys.platform != "win32" else norm_path.lower()
                is_exists = lookup_p in self.existing_paths
                item.set_category("exists" if is_exists else "new")

                if is_exists:
                    # Re-check if it was an alternative to disable edit button
                    if lookup_p in self.alternative_paths:
                        item.edit_btn.setEnabled(False)
                        item.edit_btn.setToolTip(
                            "Path exists as an alternative file for rig: '{}'".format(
                                self.existing_paths[lookup_p]
                            )
                        )
                    self.sec_exists.addWidget(item)
                else:
                    self.sec_new.addWidget(item)


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
        # Ensure orig_tags is a list
        if not isinstance(orig_tags, list):
            orig_tags = [t.strip() for t in str(orig_tags).split(",") if t.strip()]
            
        self.tags_input = TagEditor(self.tags)
        self.tags_input.setTags(orig_tags)
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
        tags = self.tags_input.getTags()

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
