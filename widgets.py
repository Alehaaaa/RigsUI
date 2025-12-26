from __future__ import absolute_import, print_function, unicode_literals
import os
import shutil
import subprocess
import logging
import sys
import re
from maya import cmds

try:
    from PySide6 import QtWidgets, QtCore, QtGui  # type: ignore

    QAction = QtGui.QAction
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui  # type: ignore

    QAction = QtWidgets.QAction

# -------------------- Logging --------------------
LOG = logging.getLogger("LibraryUI")

# -------------------- Constants --------------------
try:
    MODULE_DIR = os.path.dirname(__file__)
except NameError:
    MODULE_DIR = "/"

IMAGES_DIR = os.path.join(MODULE_DIR, "images")


def format_name(name):
    return name.lower().replace(" ", "_")


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
                # Fallback if style object is invalid or deleted
                return 10
        else:
            return parent.spacing()


# -------------------- Utility Widgets --------------------


class OpenMenu(QtWidgets.QMenu):
    def __init__(self, title=None, parent=None):
        super(OpenMenu, self).__init__(title, parent) if title else super(OpenMenu, self).__init__(
            parent
        )
        self.setSeparatorsCollapsible(False)

        if parent and hasattr(parent, "destroyed"):
            parent.destroyed.connect(self.close)

        self.triggered.connect(self._on_action_triggered)

    def _on_action_triggered(self, action):
        if isinstance(action, QtWidgets.QWidgetAction):
            return

    def mouseReleaseEvent(self, e):
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
        # Clear action
        clear_action = QAction("Clear Filters", self.menu)
        clear_action.setIcon(QtGui.QIcon(":/trash.png"))
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


class ClickableLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super(ClickableLabel, self).__init__(parent)
        self.setFixedSize(148, 148)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("border: 1px solid #444; background: #222; color: #888;")
        self._clickable = False

    def updateImageDisplay(self, object):
        img_name = object.data.get("image") or format_name(object.name) + ".jpg"
        img_path = os.path.join(IMAGES_DIR, img_name)

        if img_name and os.path.exists(img_path):
            pix = QtGui.QPixmap(img_path)
            self.setPixmap(
                pix.scaled(
                    self.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
            )
            self.setText("")
            self.setCursor(QtCore.Qt.ArrowCursor)
            self._clickable = False
        else:
            self.setPixmap(QtGui.QPixmap())
            self.setText("{}\n(Click to set image)".format(object.name))
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self._clickable = True

    def mousePressEvent(self, event):
        if self._clickable and event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
            super(ClickableLabel, self).mousePressEvent(event)


# -------------------- Custom Widgets --------------------


class RigItemWidget(QtWidgets.QFrame):
    """Widget representing a single rig."""

    imageUpdated = QtCore.Signal()
    filterRequested = QtCore.Signal(str, str)
    editRequested = QtCore.Signal(str)  # name

    def __init__(self, name, data, parent=None):
        super(RigItemWidget, self).__init__(parent)
        self.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        self.setFixedWidth(160)
        self.setFixedHeight(210)

        self.name = name
        self.data = data

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Image
        self.image_lbl = ClickableLabel()
        self.image_lbl.clicked.connect(self.change_image)
        layout.addWidget(self.image_lbl)

        self.update_image_display()

        # Name Label
        self.name_lbl = QtWidgets.QLabel(self.name)
        self.name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.name_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.name_lbl)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.add_reference_btn = QtWidgets.QPushButton()
        self.add_reference_btn.setMinimumHeight(25)
        # Style set in update_state
        # self.add_reference_btn.clicked.connect(self.add_reference) # connected dynamically
        btn_layout.addWidget(self.add_reference_btn, 2)

        self.info_btn = QtWidgets.QPushButton()
        self.info_btn.setIcon(QtGui.QIcon(":/info.png"))
        self.info_btn.setFixedSize(25, 25)
        self.info_btn.clicked.connect(self.show_info)
        btn_layout.addWidget(self.info_btn, 0)

        layout.addLayout(btn_layout)

        self._formatTooltip()

    def _formatTooltip(self):
        tooltip = "Name: {}\n".format(self.name)
        tooltip += "Author: {}\n".format(self.data.get("author") or "N/A")
        tooltip += "Link: {}\n".format(self.data.get("link") or "N/A")
        tooltip += "Collection: {}\n".format(self.data.get("collection") or "N/A")
        tooltip += "Tags: {}\n".format(self.data.get("tags") or "N/A")
        tooltip += "Path: {}".format(self.data.get("path") or "N/A")
        self.setToolTip(tooltip)

    def set_exists(self, exists):
        self.add_reference_btn.setEnabled(exists)
        if exists:
            self.update_state()
        else:
            self.add_reference_btn.setText("MISSING")
            self.add_reference_btn.setStyleSheet(
                "QPushButton { font-weight: bold; background-color: #4e524e; color: #aaa; }"
            )
            try:
                self.add_reference_btn.clicked.disconnect()
            except Exception:
                pass

    def update_state(self):
        # Check if currently referenced
        path = self.data.get("path", "")
        if path:
            norm_path = os.path.normpath(path).lower()
            is_ref = False
            try:
                # check references
                refs = cmds.file(q=True, reference=True)
                for r in refs:
                    if os.path.normpath(r).lower() == norm_path:
                        is_ref = True
                        break
            except Exception:
                pass

            try:
                self.add_reference_btn.clicked.disconnect()
            except Exception:
                pass

            if is_ref:
                self.add_reference_btn.setText("REMOVE")
                # Dark muted red
                self.add_reference_btn.setStyleSheet(
                    "QPushButton { font-weight: bold; background-color: #733e3e; color: #ddd; }"
                    + "QPushButton:hover { background-color: #8a4d4d; }"
                    + "QPushButton:pressed { background-color: #6e2f2f; }"
                )
                self.add_reference_btn.clicked.connect(self.remove_reference)
            else:
                self.add_reference_btn.setText("ADD")
                self.add_reference_btn.setStyleSheet(
                    "QPushButton { font-weight: bold; background-color: #517853; color: white; }"
                    + "QPushButton:disabled { background-color: #4e524e; }"
                    + "QPushButton:hover { background-color: #608c62; }"
                )
                self.add_reference_btn.clicked.connect(self.add_reference)

    def update_image_display(self):
        self.image_lbl.updateImageDisplay(self)

    def change_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            # Copy to images dir
            ext = os.path.splitext(path)[1]
            new_name = "{}{}".format(format_name(self.name), ext)
            dest = os.path.join(IMAGES_DIR, new_name)
            try:
                shutil.copy2(path, dest)
                self.data["image"] = new_name
                self.imageUpdated.emit()  # Notify parent to save JSON
                self.update_image_display()
            except Exception as e:
                LOG.error("Failed to copy image: {}".format(e))

    def add_reference(self):
        try:
            dialog = cmds.confirmDialog(
                title="Add Reference",
                message="Do you want to add '{}' as a reference?\nThis will add the rig to your scene.".format(
                    self.name
                ),
                button=["Reference", "Cancel"],
                defaultButton="Reference",
                cancelButton="Cancel",
                dismissString="Cancel",
            )
            if dialog == "Reference":
                self.add_reference_btn.setEnabled(False)

                path = self.data.get("path", "")
                if path and os.path.exists(path):
                    try:
                        # Basic reference logic, can be expanded
                        cmds.file(path, reference=True, namespace=self.name.replace(" ", "_"))
                        LOG.info("Referenced rig: {}".format(self.name))
                    except Exception as e:
                        LOG.error("Error referencing file: {}".format(e))
                        QtWidgets.QMessageBox.warning(
                            self, "Error", "Could not load rig: {}".format(e)
                        )
                else:
                    QtWidgets.QMessageBox.warning(
                        self, "Missing File", "Rig file not found:\n{}".format(path)
                    )
        except Exception as e:
            LOG.error("Error adding reference: {}".format(e))
            QtWidgets.QMessageBox.warning(self, "Error", "Could not add reference: {}".format(e))
        finally:
            self.add_reference_btn.setEnabled(True)
            self.update_state()

    def remove_reference(self):
        # Confirmation
        dialog = cmds.confirmDialog(
            title="Remove Reference",
            message="Are you sure you want to remove '{}'?".format(self.name),
            button=["Remove", "Cancel"],
            defaultButton="Cancel",
            cancelButton="Cancel",
            dismissString="Cancel",
        )
        if dialog == "Remove":
            path = self.data.get("path", "")
            try:
                # Remove reference
                cmds.file(path, removeReference=True)
                LOG.info("Removed reference: {}".format(self.name))
            except Exception as e:
                LOG.error("Failed to remove reference: {}".format(e))
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Could not remove reference:\n{}".format(e)
                )
            finally:
                self.update_state()

    def show_info(self):
        dlg = InfoDialog(self.name, self.data, self)
        dlg.filterRequested.connect(self.filterRequested.emit)
        dlg.editRequested.connect(lambda: self.editRequested.emit(self.name))
        dlg.exec_()


# -------------------- Custom Dialogs --------------------


class InfoDialog(QtWidgets.QDialog):
    filterRequested = QtCore.Signal(str, str)  # category, value
    editRequested = QtCore.Signal()

    def __init__(self, name, data, parent=None):
        super(InfoDialog, self).__init__(parent)
        self.setWindowTitle(name)
        self.resize(300, 400)
        self.data = data
        self.name = name

        self.__link_style = '<a href="%s" style="color: #5285a6;">%s</a>'  # Link color
        self.__filter_style = '<a href="%s" style="color: LightGray;">%s</a>'  # Filter color

        self.setup_ui()

    def setup_ui(self):
        # Main Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Image
        img_name = self.data.get("image") or format_name(self.name) + ".jpg"
        img_path = os.path.join(IMAGES_DIR, img_name)

        self.image_lbl = QtWidgets.QLabel()
        self.image_lbl.setFixedSize(200, 200)
        self.image_lbl.setAlignment(QtCore.Qt.AlignCenter)
        # Minimal style for image container
        self.image_lbl.setStyleSheet("background-color: #222; border: 1px solid #444;")

        if img_name and os.path.exists(img_path):
            pix = QtGui.QPixmap(img_path)
            self.image_lbl.setPixmap(
                pix.scaled(
                    self.image_lbl.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
            )
        else:
            self.image_lbl.setText("No Image")

        layout.addWidget(self.image_lbl, 0, QtCore.Qt.AlignHCenter)

        # Name
        name_lbl = QtWidgets.QLabel(self.name)
        # Native font size, just bold
        font = name_lbl.font()
        font.setBold(True)
        font.setPointSize(12)
        name_lbl.setFont(font)
        name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(name_lbl)

        # Info Container - Removed Frame Styling
        info_layout = QtWidgets.QFormLayout()
        info_layout.setLabelAlignment(QtCore.Qt.AlignRight)
        info_layout.setSpacing(5)

        def add_row(label, value, is_link=False, is_path=False, filter_category=None):
            if not value and not filter_category:
                value = "N/A"

            lbl = QtWidgets.QLabel()
            lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

            if is_link and value != "N/A":
                if not value.startswith("http"):
                    href = "http://" + value
                else:
                    href = value
                text = self.__link_style % (href, href)
                lbl.setText(text)
                lbl.setOpenExternalLinks(True)
            elif is_path and value != "N/A":
                # Make path short and clickable
                text = self.__link_style % (value, value)
                lbl.setText(text)
                lbl.setToolTip("Click to open folder")
                lbl.linkActivated.connect(self.open_folder)
                lbl.setWordWrap(True)
            elif filter_category:
                # Handle Collection (string) and Tags (list)
                if isinstance(value, list):
                    # Tags
                    if not value:
                        lbl.setText("N/A")
                    else:
                        links = []
                        for item in value:
                            links.append(self.__filter_style % (item, item))
                        lbl.setText(", ".join(links))
                        lbl.linkActivated.connect(lambda v: self.handle_filter(filter_category, v))
                else:
                    # Collection
                    display_text = value if value else "Empty"
                    # If it's effectively empty/None, we map it to "Empty" for filtering purposes
                    filter_val = value if value else "Empty"

                    text = self.__filter_style % (filter_val, display_text)
                    lbl.setText(text)
                    lbl.linkActivated.connect(lambda v: self.handle_filter(filter_category, v))
            else:
                lbl.setText(str(value))
                lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
                lbl.setWordWrap(True)

            # Helper for label style
            label_widget = QtWidgets.QLabel(label + ":")
            # Default style usage

            info_layout.addRow(label_widget, lbl)

        add_row("Author", self.data.get("author"))
        add_row("Link", self.data.get("link"), is_link=True)
        add_row("Collection", self.data.get("collection"), filter_category="Collections")
        add_row("Tags", self.data.get("tags", []), filter_category="Tags")

        add_row("Path", self.data.get("path"), is_path=True)

        layout.addLayout(info_layout)

        layout.addStretch()

        # Close Button
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)

        self.edit_btn = QtWidgets.QPushButton("Edit")
        self.edit_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.edit_btn.setToolTip("Edit Rig Details")
        self.edit_btn.clicked.connect(self.request_edit)
        btn_layout.addWidget(self.edit_btn, 1)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn, 2)

        layout.addLayout(btn_layout)

    def request_edit(self):
        self.editRequested.emit()
        self.accept()

    def handle_filter(self, category, value):
        self.filterRequested.emit(category, value)
        self.accept()

    def open_folder(self, path):
        path = os.path.normpath(path)

        # If the path points to a file, get the directory
        folder_to_open = path
        if os.path.isfile(path):
            folder_to_open = os.path.dirname(path)

        if not os.path.exists(folder_to_open):
            QtWidgets.QMessageBox.warning(self, "Error", "Path does not exist:\n" + folder_to_open)
            return

        try:
            if sys.platform == "win32":
                os.startfile(folder_to_open)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder_to_open])
            else:
                subprocess.Popen(["xdg-open", folder_to_open])
        except Exception as e:
            LOG.error("Failed to open folder: {}".format(e))
            QtWidgets.QMessageBox.warning(self, "Error", "Could not open folder:\n{}".format(e))


class TagsLineEdit(QtWidgets.QLineEdit):
    def __init__(self, tags, parent=None):
        super(TagsLineEdit, self).__init__(parent)
        self.tags = tags
        self.completer = QtWidgets.QCompleter(self.tags, self)
        self.completer.setWidget(self)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion)

    def keyPressEvent(self, event):
        super(TagsLineEdit, self).keyPressEvent(event)

        # Check completion
        text = self.text()[: self.cursorPosition()]
        if not text:
            self.completer.popup().hide()
            return

        prefix = text.split(",")[-1].strip()

        if len(prefix) > 0:
            self.completer.setCompletionPrefix(prefix)
            if self.completer.completionCount() > 0:
                cr = self.cursorRect()
                cr.setWidth(
                    self.completer.popup().sizeHintForColumn(0)
                    + self.completer.popup().verticalScrollBar().sizeHint().width()
                )
                self.completer.complete(cr)
            else:
                self.completer.popup().hide()
        else:
            self.completer.popup().hide()

    def insert_completion(self, completion):
        text = self.text()
        cursor_pos = self.cursorPosition()
        prefix_len = len(text[:cursor_pos].split(",")[-1].strip())

        # Remove prefix
        text_before = text[: cursor_pos - prefix_len]
        text_after = text[cursor_pos:]

        # Add completion + ", "
        new_text = text_before + completion + ", " + text_after
        self.setText(new_text)


class RigSetupDialog(QtWidgets.QDialog):
    def __init__(
        self,
        existing_names,
        collections,
        authors,
        tags,  # Added
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
        self.file_path = file_path if file_path else self.rig_data.get("path", "")
        self.existing_names = existing_names
        self.collections = collections
        self.authors = authors
        self.tags = tags  # Added
        self.result_data = None

        title = "Add New Rig" if mode == "add" else "Edit Rig: {}".format(rig_name)
        self.setWindowTitle(title)
        self.resize(300, 450)

        self.image_path = ""

        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Image ---
        self.image_lbl = QtWidgets.QLabel("No Image\n(Click to set)")
        self.image_lbl.setFixedSize(150, 150)
        self.image_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.image_lbl.setStyleSheet(
            "background-color: #222; border: 1px solid #555; border-radius: 5px;"
        )
        self.image_lbl.setCursor(QtCore.Qt.PointingHandCursor)
        self.image_lbl.mousePressEvent = self.on_image_click

        # Pre-fill Image if edit
        current_img = self.rig_data.get("image")
        if current_img:
            img_path = os.path.join(IMAGES_DIR, current_img)
            if os.path.exists(img_path):
                pix = QtGui.QPixmap(img_path)
                self.image_lbl.setPixmap(
                    pix.scaled(
                        self.image_lbl.size(),
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                )
                self.image_lbl.setText("")

        layout.addWidget(self.image_lbl, 0, QtCore.Qt.AlignHCenter)

        # --- Form ---
        form_layout = QtWidgets.QFormLayout()

        # Name
        self.name_le = QtWidgets.QLineEdit()
        if self.mode == "add" and self.file_path:
            filename = os.path.basename(self.file_path)
            base_name = os.path.splitext(filename)[0]
            base_name = base_name.replace("_", " ")
            self.name_le.setText(base_name)
        elif self.mode == "edit" and self.rig_name:
            self.name_le.setText(self.rig_name)

        self.name_le.textChanged.connect(self.validate_name)
        form_layout.addRow("Name*:", self.name_le)

        # Tags
        self.tags_le = TagsLineEdit(self.tags)  # Use custom widget
        self.tags_le.setPlaceholderText("human, male, ...")
        if self.mode == "edit":
            tags = self.rig_data.get("tags", [])
            if tags:
                self.tags_le.setText(", ".join(tags) + ", ")
        form_layout.addRow("Tags:", self.tags_le)

        # Collection
        self.coll_le = QtWidgets.QLineEdit()
        if self.collections:
            completer = QtWidgets.QCompleter(self.collections)
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.coll_le.setCompleter(completer)
        if self.mode == "edit":
            self.coll_le.setText(self.rig_data.get("collection", ""))
        form_layout.addRow("Collection:", self.coll_le)

        # Author
        self.author_le = QtWidgets.QLineEdit()
        if self.authors:
            completer = QtWidgets.QCompleter(self.authors)
            completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.author_le.setCompleter(completer)
        if self.mode == "edit":
            self.author_le.setText(self.rig_data.get("author", ""))
        form_layout.addRow("Author:", self.author_le)

        # Link
        self.link_le = QtWidgets.QLineEdit()
        if self.mode == "edit":
            self.link_le.setText(self.rig_data.get("link", ""))
        form_layout.addRow("Link:", self.link_le)

        layout.addLayout(form_layout)

        layout.addStretch()

        # --- Buttons ---
        btn_layout = QtWidgets.QHBoxLayout()

        btn_text = "Add" if self.mode == "add" else "Save"
        self.ok_btn = QtWidgets.QPushButton(btn_text)
        self.ok_btn.clicked.connect(self.accept_data)
        btn_layout.addWidget(self.ok_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        # Initial validation
        self.validate_name()

    def on_image_click(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select Image", "", "Images (*.png *.jpg *.jpeg)"
            )
            if path:
                self.image_path = path
                pix = QtGui.QPixmap(path)
                self.image_lbl.setPixmap(
                    pix.scaled(
                        self.image_lbl.size(),
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                )
                self.image_lbl.setText("")

    def validate_name(self):
        name = self.name_le.text().strip()
        if not name:
            self.ok_btn.setEnabled(False)
            self.ok_btn.setToolTip("Name is required")
        elif name in self.existing_names and name != self.rig_name:  # Allow own name if edit
            self.ok_btn.setEnabled(False)
            self.ok_btn.setToolTip("Name already exists")
        else:
            self.ok_btn.setEnabled(True)
            self.ok_btn.setToolTip("")

    def accept_data(self):
        name = self.name_le.text().strip()

        # Process tags
        tags_str = self.tags_le.text()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]

        image_name = self.rig_data.get("image", "")

        if self.image_path and os.path.exists(self.image_path):
            try:
                # Sanitize name for filename: lowercase, underscores, ascii only
                # Replace spaces with underscores first
                base_clean = format_name(name)
                # Remove anything that is not alphanumeric or underscore
                safe_name = re.sub(r"[^a-z0-9_]", "", base_clean)

                image_filename = "{}.jpg".format(safe_name)
                dest_path = os.path.join(IMAGES_DIR, image_filename)

                # Convert and Save using QImage
                img = QtGui.QImage(self.image_path)
                if not img.isNull():
                    # Ensure images dir exists (just in case)
                    if not os.path.exists(IMAGES_DIR):
                        os.makedirs(IMAGES_DIR)

                    img.save(dest_path, "JPG")
                    image_name = image_filename
                else:
                    LOG.error("Failed to load image for conversion: {}".format(self.image_path))

            except Exception as e:
                LOG.error("Failed to process image: {}".format(e))

        self.result_data = {
            "name": name,
            "data": {
                "path": self.file_path,
                "image": image_name,
                "tags": tags or "N/A",
                "collection": self.coll_le.text().strip() or "N/A",
                "author": self.author_le.text().strip() or "N/A",
                "link": self.link_le.text().strip() or "N/A",
            },
            "image_source": None,  # Handled locally now
        }
        self.accept()
