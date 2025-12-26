# -*- coding: utf-8 -*-
import os
import re
import io
import sys
import json
import logging
from .widgets import FilterMenu, FlowLayout, RigItemWidget, RigSetupDialog

import maya.cmds as cmds  # type: ignore
from . import utils

try:
    from PySide6 import QtWidgets, QtCore, QtGui  # type: ignore
    from shiboken6 import wrapInstance  # type: ignore
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui  # type: ignore
    from shiboken2 import wrapInstance  # type: ignore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin  # type: ignore
from maya.OpenMayaUI import MQtUtil  # type: ignore


# -------------------- Logging --------------------
LOG = logging.getLogger("LibraryUI")
if not LOG.handlers:
    h = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("[LibraryUI] %(levelname)s: %(message)s")
    h.setFormatter(formatter)
    LOG.addHandler(h)
LOG.setLevel(logging.DEBUG)
LOG.disabled = True

# -------------------- Constants --------------------
TOOL_TITLE = "Rigs Library"
try:
    with io.open(os.path.join(utils.MODULE_DIR, "VERSION"), "r", encoding="utf-8") as f:
        VERSION = f.read().strip()
except Exception:
    VERSION = "0.0.3 alpha"

RIGS_JSON = os.path.join(utils.MODULE_DIR, "rigs.json")

# Ensure images dir exists
if not os.path.exists(utils.IMAGES_DIR):
    os.makedirs(utils.IMAGES_DIR)


# -------------------- Utils --------------------
def _get_maya_main_window():
    ptr = MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


# -------------------- Main Window --------------------


class LibraryUI(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    TOOL_TITLE = TOOL_TITLE
    TOOL_OBJECT_NAME = TOOL_TITLE.replace(" ", "")
    WINDOW_TITLE = "{} v{}".format(TOOL_TITLE, VERSION)
    WORKSPACE_CONTROL_NAME = "{}WorkspaceControl".format(TOOL_OBJECT_NAME)

    def __init__(self, parent=None):
        parent = parent or _get_maya_main_window()
        super(LibraryUI, self).__init__(parent)
        self.setObjectName(self.TOOL_OBJECT_NAME)
        self.settings = QtCore.QSettings(self.TOOL_TITLE, None)

        self.__opened = True
        self.rig_data = {}

        self._build_ui()
        self.load_data()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- Top Bar ---
        top_layout = QtWidgets.QHBoxLayout()

        # Search
        self.search_le = QtWidgets.QLineEdit()
        self.search_le.setFixedHeight(25)
        self.search_le.setPlaceholderText("Search rigs...")
        self.search_le.textChanged.connect(self.refresh_grid)
        top_layout.addWidget(self.search_le)

        # Add Rig Button
        self.add_btn = QtWidgets.QPushButton()
        self.add_btn.setIcon(utils.get_icon("add.svg"))
        self.add_btn.setFixedSize(25, 25)
        self.add_btn.setToolTip("Add new rig from file")
        self.add_btn.clicked.connect(self.add_new_rig)
        top_layout.insertWidget(0, self.add_btn)  # Insert at left

        # Filters
        self.filter_menu = FilterMenu("Filters")
        self.filter_menu.setFixedHeight(25)
        self.filter_menu.setToolTip("Filter rigs by category")
        self.filter_menu.selectionChanged.connect(self.refresh_grid)
        top_layout.addWidget(self.filter_menu)

        # Reload
        self.reload_btn = QtWidgets.QPushButton("Reload")
        self.reload_btn.setIcon(utils.get_icon("refresh.svg"))
        self.reload_btn.setFixedHeight(25)
        self.reload_btn.setToolTip("Reload rig data from disk")
        self.reload_btn.clicked.connect(lambda: self.load_data(delay=True))
        top_layout.addWidget(self.reload_btn)

        main_layout.addLayout(top_layout)

        # --- Scroll Area ---
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.container = QtWidgets.QWidget()
        self.flow_layout = FlowLayout(self.container)

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

    def load_data(self, delay=False):
        """Loads data from rigs.json and populates UI."""
        if os.path.exists(RIGS_JSON):
            try:
                with io.open(RIGS_JSON, "r", encoding="utf-8") as f:
                    self.rig_data = json.load(f)
            except Exception as e:
                LOG.error("Failed to load JSON: {}".format(e))
                self.rig_data = {}
        else:
            self.rig_data = {}

        # Scan for unique tags and collections
        collections = set()
        all_tags = set()
        authors = set()

        empty_collection = False

        for details in self.rig_data.values():
            val = details.get("collection")
            if val:
                collections.add(val)
            else:
                empty_collection = True
            if "tags" in details:
                for t in details.get("tags", []):
                    if t:
                        all_tags.add(t)
            if "author" in details:
                authors.add(details.get("author"))
            details["exists"] = bool(os.path.exists(details.get("path", "")))

        collections = sorted(list(collections))
        if empty_collection:
            collections = ["Empty"] + collections

        all_tags = sorted(list(all_tags))

        self.filter_menu.set_items(
            sections={"Tags": all_tags, "Collections": collections, "Author": authors}
        )

        self.load_filters()
        self.refresh_grid(delay)

    def save_data(self):
        try:
            with io.open(RIGS_JSON, "w", encoding="utf-8") as f:
                json.dump(self.rig_data, f, indent=4)
        except Exception as e:
            LOG.error("Failed to save JSON: {}".format(e))

    def add_new_rig(self):
        """Opens dialog to add a new rig."""
        file_filter = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Rig File", "", file_filter)

        if not path:
            return

        path = os.path.normpath(path)

        # Check if already exists (by path)
        for name, data in self.rig_data.items():
            existing_path = os.path.normpath(data.get("path", ""))
            if existing_path == path:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Duplicate",
                    "This file is already in the library as '{}'.".format(name),
                )
                return

        # Prepare autocomplete data
        collections = set()
        authors = set()
        all_tags = set()
        for details in self.rig_data.values():
            if details.get("collection"):
                collections.add(details.get("collection"))
            if details.get("author"):
                authors.add(details.get("author"))
            if details.get("tags"):
                all_tags.update(details.get("tags"))

        existing_names = list(self.rig_data.keys())

        dlg = RigSetupDialog(
            existing_names,
            sorted(list(collections)),
            sorted(list(authors)),
            sorted(list(all_tags)),
            mode="add",
            file_path=path,
            parent=self,
        )
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            result = dlg.result_data
            if result:
                new_name = result["name"]
                new_data = result["data"]

                # So we just update data
                self.rig_data[new_name] = new_data
                self.save_data()
                self.load_data(delay=False)

    def edit_rig(self, rig_name):
        """Opens dialog to edit an existing rig."""
        if rig_name not in self.rig_data:
            return

        data = self.rig_data[rig_name]

        # Prepare autocomplete data
        collections = set()
        authors = set()
        all_tags = set()
        for details in self.rig_data.values():
            if details.get("collection"):
                collections.add(details.get("collection"))
            if details.get("author"):
                authors.add(details.get("author"))
            if details.get("tags"):
                all_tags.update(details.get("tags"))

        existing_names = list(self.rig_data.keys())

        dlg = RigSetupDialog(
            existing_names,
            sorted(list(collections)),
            sorted(list(authors)),
            sorted(list(all_tags)),
            mode="edit",
            rig_name=rig_name,
            rig_data=data,
            parent=self,
        )

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            result = dlg.result_data
            if result:
                new_name = result["name"]
                new_data = result["data"]

                # Handle Rename
                if new_name != rig_name:
                    del self.rig_data[rig_name]

                self.rig_data[new_name] = new_data
                self.save_data()
                self.load_data(delay=True)

    def apply_single_filter(self, category, value):
        """Sets a single filter active, clearing others."""
        self.filter_menu.set_selected({category: [value]})
        self.refresh_grid()

    def refresh_grid(self, delay=False):
        # Clear existing
        self._clear_layout(self.flow_layout)

        # Filter out symbols (replace for spaces) from search text
        search_txt = self.search_le.text().lower()
        search_txt = re.sub(r"[^a-zA-Z0-9]", " ", search_txt)

        sel_filters = self.filter_menu.get_selected()

        if delay:
            cmds.waitCursor(state=True)
        try:
            velocity = 200 / len(self.rig_data) * 2
            for name, data in self.rig_data.items():
                # UI closed → stop immediately
                if not self.__opened:
                    break

                # 1. Search Text
                if search_txt and not any(s in name.lower() for s in search_txt.split()):
                    continue

                # 2. Collections
                if sel_filters.get("Collections"):
                    rig_coll = data.get("collection")
                    match = (rig_coll and rig_coll in sel_filters.get("Collections")) or (
                        not rig_coll and "Empty" in sel_filters.get("Collections")
                    )
                    if not match:
                        continue

                # 3. Tags
                if sel_filters.get("Tags"):
                    rig_tags = set(data.get("tags", []))
                    if not rig_tags.intersection(sel_filters.get("Tags")):
                        continue

                # 4. Author
                if sel_filters.get("Author"):
                    rig_author = data.get("author")
                    if rig_author and rig_author not in sel_filters.get("Author"):
                        continue

                if delay:
                    loop = QtCore.QEventLoop()
                    QtCore.QTimer.singleShot(velocity, loop.quit)
                    loop.exec_()

                # Add Widget
                try:
                    wid = RigItemWidget(name, data)
                    wid.imageUpdated.connect(self.save_data)
                    wid.filterRequested.connect(self.apply_single_filter)
                    wid.editRequested.connect(self.edit_rig)
                    wid.set_exists(data["exists"])
                    self.flow_layout.addWidget(wid)
                except Exception as e:
                    LOG.error("Failed to create widget for rig '{}': {}".format(name, e))
        except Exception as e:
            LOG.error("Failed to refresh grid: {}".format(e))
        finally:
            if delay:
                cmds.waitCursor(state=False)

        self.save_filters()

    @staticmethod
    def _clear_layout(layout):
        """
        Clears a given layout by removing all widgets and deleting them
        :param layout: The layout to clear
        :return: None
        """
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    # ---------- API ----------

    def set_windowPosition(self):
        """
        Restores or initializes the dock/floating position of the workspace control.
        """
        floating = self.settings.value("floating", False)
        position = self.settings.value("position", None)
        size = self.settings.value("size", None)

        kwargs = {
            "e": True,
            "label": self.WINDOW_TITLE,
            "minimumWidth": 370,
            "retain": False,
        }

        # If floating, restore previous floating geometry
        if floating:
            kwargs["floating"] = True
        else:
            # Try to dock next to a known panel
            dock_target = None
            for ctl in ("ChannelBoxLayerEditor", "AttributeEditor"):
                if cmds.control(ctl, exists=True):
                    dock_target = ctl
                    break

            if dock_target:
                kwargs["tabToControl"] = [dock_target, -1]
                LOG.info("Docking to: {}".format(dock_target))
            else:
                LOG.info("No valid dock target found; defaulting to floating.")
                kwargs["floating"] = True

        try:
            cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, **kwargs)
            LOG.info("Workspace control positioned: floating={}".format(floating))
        except Exception as e:
            LOG.error("Error positioning workspace control: {}".format(e))

        try:
            if floating and position and size:
                ptr = MQtUtil.findControl(self.WORKSPACE_CONTROL_NAME)
                qt_control = wrapInstance(int(ptr), QtWidgets.QWidget).window()

                LOG.info("Setting workspace control position: {}".format(position))
                LOG.info("Setting workspace control size: {}".format(size))
                qt_control.setGeometry(
                    QtCore.QRect(int(position[0]), int(position[1]), int(size[0]), int(size[1]))
                )
        except Exception as e:
            LOG.error("Error setting workspace control geometry: {}".format(e))

    def save_windowPosition(self):
        """
        Saves the current window state (floating or docked), position, and size.
        """
        try:
            if not cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, exists=True):
                return LOG.warning("No workspace control found to save position.")

            # Check if the workspace control is floating or docked
            floating = cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, q=True, floating=True)
            LOG.info("Workspace control is {}".format("floating" if floating else "docked"))
            self.settings.setValue("floating", floating)

            if floating:
                ptr = MQtUtil.findControl(self.WORKSPACE_CONTROL_NAME)
                qt_control = wrapInstance(int(ptr), QtWidgets.QWidget)
                geo = qt_control.geometry()
                top_left_global = qt_control.mapToGlobal(geo.topLeft())

                position = (top_left_global.x(), top_left_global.y())
                size = (geo.width(), geo.height())

                self.settings.setValue("position", position)
                self.settings.setValue("size", size)
                LOG.info("Saved floating position {} size {}".format(position, size))
            else:
                # Optionally save dock area for docked panels
                try:
                    dock_area = cmds.workspaceControl(
                        self.WORKSPACE_CONTROL_NAME, q=True, dockArea=True
                    )
                    self.settings.setValue("dockArea", dock_area)
                    LOG.info("Saved docked area: {}".format(dock_area))
                except Exception:
                    LOG.debug("Dock area not available to save.")

            self.settings.sync()  # Force settings to write immediately
            LOG.info("Window position saved successfully.")

        except Exception as e:
            LOG.error("Error saving window position: {}".format(e))

    def save_filters(self):
        """Save the current filters to the settings."""
        try:
            sel_filters = self.filter_menu.get_selected()
            self.settings.setValue("filters", sel_filters)
            LOG.info("Filters saved successfully.")
        except Exception as e:
            LOG.error("Error saving filters: {}".format(e))

    def load_filters(self):
        """Load the saved filters from the settings."""
        try:
            LOG.info(self.settings.value("filters", []))
            self.filter_menu.set_selected(self.settings.value("filters", []))
            LOG.info("Filters loaded successfully.")
        except Exception as e:
            LOG.error("Error loading filters: {}".format(e))

    def dockCloseEventTriggered(self):
        """Called automatically when the dockable workspace is closed."""
        self.__opened = False
        self.save_windowPosition()
        self.save_filters()

        self._cleanup()

    def _cleanup(self):
        """Remove workspace and disconnect widget."""
        try:
            if cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, exists=True):
                cmds.deleteUI(self.WORKSPACE_CONTROL_NAME)
        except Exception:
            pass
        self.setParent(None)
        self.deleteLater()

    @classmethod
    def showUI(cls):
        # Close previous instance if exists
        for ui in [cls.WORKSPACE_CONTROL_NAME]:
            try:
                if cmds.workspaceControl(ui, exists=True):
                    cmds.deleteUI(ui)
            except Exception:
                pass

        inst = cls(_get_maya_main_window())
        inst.show(dockable=True, retain=False)

        inst.set_windowPosition()
        return inst


def _get_maya_main_window():
    ptr = MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)
