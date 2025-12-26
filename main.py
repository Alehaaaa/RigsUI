# -*- coding: utf-8 -*-
import os
import io
import sys
import json
import logging
from .widgets import FilterMenu, FlowLayout, RigItemWidget, RigSetupDialog, SortMenu

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

RIGS_JSON = os.path.join(utils.MODULE_DIR, "rigs_database.json")

# Ensure images dir exists
if not os.path.exists(utils.IMAGES_DIR):
    os.makedirs(utils.IMAGES_DIR)


# -------------------- Utils --------------------
def _get_maya_main_window():
    ptr = MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


# -------------------- Search Worker --------------------

class SearchWorker(QtCore.QObject):
    """
    Background worker for filtering rigs based on search text and category filters.
    Runs in a separate QThread to avoid freezing the main UI.
    """
    finished = QtCore.Signal(list)

    def __init__(self, rig_data, search_text, filters):
        super(SearchWorker, self).__init__()
        self.rig_data = rig_data
        self.search_text = search_text
        self.filters = filters
        self._is_running = True

    def run(self):
        visible_names = []
        try:
            raw_search = self.search_text.lower()
            search_tokens = raw_search.split()

            # Parse query
            field_filters = {}
            general_terms = []

            for token in search_tokens:
                if ":" in token:
                    key, val = token.split(":", 1)
                    # Normalize keys
                    if key in ["t", "tag", "tags"]:
                        key = "tags"
                    elif key in ["a", "auth", "author"]:
                        key = "author"
                    elif key in ["c", "col", "collection"]:
                        key = "collection"
                    elif key in ["l", "link"]:
                        key = "link"
                    
                    known_fields = ["tags", "author", "collection", "link"]
                    if key in known_fields:
                        if key not in field_filters:
                            field_filters[key] = []
                        field_filters[key].append(val)
                    else:
                        general_terms.append(token)
                else:
                    general_terms.append(token)

            for name, data in self.rig_data.items():
                if not self._is_running:
                    return

                # Check Field Filters
                match_fields = True
                for key, vals in field_filters.items():
                    data_val = data.get(key)
                    
                    if key == "tags":
                         if not data_val: 
                             match_fields = False; break
                         data_tags_lower = [t.lower() for t in data_val]
                         for v in vals:
                             if v not in data_tags_lower:
                                 match_fields = False; break
                    else:
                         if not data_val:
                             match_fields = False; break
                         data_val_lower = data_val.lower()
                         for v in vals:
                             if v not in data_val_lower:
                                 match_fields = False; break
                    
                    if not match_fields: break
                
                if not match_fields: continue

                # Check General Terms (Name search)
                match_general = True
                if general_terms:
                    name_lower = name.lower()
                    for term in general_terms:
                        if term not in name_lower:
                            match_general = False; break
                
                if not match_general: continue

                # Check Dropdown Filters
                match_dropdown = True
                sel = self.filters

                # Collections
                if sel.get("Collections"):
                    rig_coll = data.get("collection")
                    # Match if in selection OR (is effectively empty AND "Empty" selected)
                    is_match = (rig_coll and rig_coll in sel.get("Collections")) or (
                        (not rig_coll or rig_coll == "Empty") and "Empty" in sel.get("Collections")
                    )
                    if not is_match:
                        match_dropdown = False

                # Tags
                if match_dropdown and sel.get("Tags"):
                    rig_tags = set(data.get("tags", []))
                    if not rig_tags.intersection(sel.get("Tags")):
                        match_dropdown = False

                # Author
                if match_dropdown and sel.get("Author"):
                    rig_author = data.get("author")
                    is_match = (rig_author and rig_author in sel.get("Author")) or (
                        (not rig_author or rig_author == "Empty") and "Empty" in sel.get("Author")
                    )
                    if not is_match:
                        match_dropdown = False
                
                if match_dropdown:
                    visible_names.append(name)

        except Exception as e:
            LOG.error("Search worker error: {}".format(e))
        
        self.finished.emit(visible_names)

    def stop(self):
        self._is_running = False


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

        self.rig_data = {}
        self._widgets_map = {} # Cache for widgets: {name: RigItemWidget}
        
        # Threading
        self._search_thread = None
        self._search_worker = None

        self._build_ui()
        self.load_data()

    # ---------- UI Setup ----------

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # Top Bar
        top_layout = QtWidgets.QHBoxLayout()

        # Add Button
        self.add_btn = QtWidgets.QPushButton()
        self.add_btn.setIcon(utils.get_icon("add.svg"))
        self.add_btn.setFixedSize(25, 25)
        self.add_btn.setToolTip("Add new rig from file")
        self.add_btn.clicked.connect(self.add_new_rig)
        top_layout.addWidget(self.add_btn)

        # Search
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setFixedHeight(25)
        self.search_input.setPlaceholderText("Search name, tag:human, collection:M-Bundle...")
        self.search_input.textChanged.connect(self.trigger_search)
        top_layout.addWidget(self.search_input)

        # Filters
        self.filter_menu = FilterMenu("Filters")
        self.filter_menu.setFixedHeight(25)
        self.filter_menu.setToolTip("Filter rigs by category")
        self.filter_menu.selectionChanged.connect(self.trigger_search)
        top_layout.addWidget(self.filter_menu)

        # Sort
        self.sort_menu = SortMenu("Sort")
        self.sort_menu.setFixedHeight(25)
        self.sort_menu.setToolTip("Sort rigs")
        self.sort_menu.sortChanged.connect(self._populate_grid)
        top_layout.addWidget(self.sort_menu)

        # Reload
        self.reload_btn = QtWidgets.QPushButton("Reload")
        self.reload_btn.setIcon(utils.get_icon("refresh.svg"))
        self.reload_btn.setFixedHeight(25)
        self.reload_btn.setToolTip("Reload rig data from disk")
        self.reload_btn.clicked.connect(lambda: self.load_data())
        top_layout.addWidget(self.reload_btn)

        main_layout.addLayout(top_layout)

        # Scroll Area
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.container = QtWidgets.QWidget()
        self.flow_layout = FlowLayout(self.container)

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

    # ---------- Data Management ----------

    def load_data(self, delay=False):
        """Loads data from JSON and updates the UI filter menus and grid."""
        if os.path.exists(RIGS_JSON):
            try:
                with io.open(RIGS_JSON, "r", encoding="utf-8") as f:
                    self.rig_data = json.load(f)
            except Exception as e:
                LOG.error("Failed to load JSON: {}".format(e))
                self.rig_data = {}
        else:
            self.rig_data = {}

        # Scan for metadata
        collections = set()
        all_tags = set()
        authors = set()

        has_empty_collection = False

        for details in self.rig_data.values():
            # Collections
            val = details.get("collection")
            if val and val != "Empty":
                collections.add(val)
            else:
                has_empty_collection = True
            
            # Tags
            for t in details.get("tags", []):
                if t: all_tags.add(t)
            
            # Authors
            val_auth = details.get("author")
            if val_auth and val_auth != "Empty":
                authors.add(val_auth)
            
            # Update File Existence
            details["exists"] = bool(os.path.exists(details.get("path", "")))

        # Update Filter Menus
        cols_sorted = sorted(list(collections))
        if has_empty_collection:
            cols_sorted = ["Empty"] + cols_sorted

        self.filter_menu.set_items(
            sections={
                "Tags": sorted(list(all_tags)), 
                "Collections": cols_sorted, 
                "Author": sorted(list(authors))
            }
        )

        self.load_filters()
        self._populate_grid()

    def save_data(self):
        """Saves current rig_data to JSON."""
        try:
            with io.open(RIGS_JSON, "w", encoding="utf-8") as f:
                json.dump(self.rig_data, f, indent=4)
        except Exception as e:
            LOG.error("Failed to save JSON: {}".format(e))

    def _populate_grid(self):
        """
        Populate the grid with widgets.
        Uses a reconciliation strategy to reuse widgets and avoid UI flicker.
        """
        if not hasattr(self, "_widgets_map"):
            self._widgets_map = {}

        # 1. Remove stale widgets
        current_names = set(self.rig_data.keys())
        cached_names = set(self._widgets_map.keys())
        to_remove = cached_names - current_names

        for name in to_remove:
            wid = self._widgets_map.pop(name)
            if wid:
                self.flow_layout.removeWidget(wid)
                wid.setParent(None)
                wid.deleteLater()

        # 2. Detach all remaining widgets from layout (to re-sort)
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            # Do not delete, just remove from layout list

        # 3. Determine Sort Order
        sort_mode, ascending = self.sort_menu.get_current_sort()
        
        def sort_key_func(item):
            name, data = item
            if sort_mode == "Collection":
                val = data.get("collection")
                # Treat "Empty" or None as "" so it sorts at the extreme
                if not val or val == "Empty":
                    val = "" 
                return (val.lower(), name.lower())
            elif sort_mode == "Author":
                val = data.get("author")
                if not val or val == "Empty":
                    val = ""
                return (val.lower(), name.lower())
            return name.lower()

        sorted_items = sorted(self.rig_data.items(), key=sort_key_func, reverse=not ascending)

        # 4. Re-add widgets in order
        for name, data in sorted_items:
            if name in self._widgets_map:
                # Reuse
                wid = self._widgets_map[name]
                wid.data = data
                wid.set_exists(data["exists"])
                wid.update_image_display()
                if hasattr(wid, "_formatTooltip"):
                    wid._formatTooltip()
            else:
                # Create
                try:
                    wid = RigItemWidget(name, data, parent=self.container)
                    wid.imageUpdated.connect(self.save_data)
                    wid.filterRequested.connect(self.apply_single_filter)
                    wid.editRequested.connect(self.edit_rig)
                    wid.set_exists(data["exists"])
                    self._widgets_map[name] = wid
                except Exception as e:
                    LOG.error("Failed to create widget '{}': {}".format(name, e))
                    continue
            
            self.flow_layout.addWidget(wid)
            wid.setVisible(True) # Ensure visible before search filter runs

        # Apply Search
        self.trigger_search()

    # ---------- Search & Filtering ----------

    def trigger_search(self):
        """Start background search worker."""
        if self._search_thread:
            try:
                if self._search_thread.isRunning():
                    if self._search_worker: self._search_worker.stop()
                    self._search_thread.quit()
                    self._search_thread.wait()
            except RuntimeError:
                pass 

        search_text = self.search_input.text()
        filters = self.filter_menu.get_selected()

        self._search_thread = QtCore.QThread()
        self._search_worker = SearchWorker(self.rig_data, search_text, filters)
        self._search_worker.moveToThread(self._search_thread)
        
        self._search_thread.started.connect(self._search_worker.run)
        self._search_worker.finished.connect(self._on_search_finished)
        self._search_worker.finished.connect(self._search_thread.quit)
        self._search_worker.finished.connect(self._search_worker.deleteLater)
        self._search_thread.finished.connect(self._search_thread.deleteLater)

        self._search_thread.start()

    def _on_search_finished(self, visible_names):
        """Apply search results to widget visibility."""
        visible_set = set(visible_names)
        
        for name, wid in self._widgets_map.items():
            should_show = name in visible_set
            if wid.isVisible() != should_show:
                wid.setVisible(should_show)
        
        # Force layout refresh
        self.flow_layout.invalidate()
        self.container.update()
        if self.container.layout():
            self.container.layout().activate()
            
        self.save_filters()

    def apply_single_filter(self, category, value):
        self.filter_menu.set_selected({category: [value]})
        self.trigger_search()

    # ---------- Rig Management (Add/Edit) ----------

    def _get_autocomplete_data(self):
        """Helper to gather unique collections, authors, and tags from current data."""
        collections = set()
        authors = set()
        all_tags = set()
        
        for details in self.rig_data.values():
            if details.get("collection"): collections.add(details.get("collection"))
            if details.get("author"): authors.add(details.get("author"))
            if details.get("tags"): all_tags.update(details.get("tags"))
            
        return sorted(list(collections)), sorted(list(authors)), sorted(list(all_tags))

    def _open_setup_dialog(self, mode, file_path=None, rig_name=None, rig_data=None):
        """Shared logic for opening the add/edit dialog."""
        cols, auths, tags = self._get_autocomplete_data()
        existing_names = list(self.rig_data.keys())

        dlg = RigSetupDialog(
            existing_names=existing_names,
            collections=cols,
            authors=auths,
            tags=tags,
            mode=mode,
            file_path=file_path,
            rig_name=rig_name,
            rig_data=rig_data,
            parent=self,
        )
        
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            result = dlg.result_data
            if result:
                new_name = result["name"]
                new_data = result["data"]
                
                # If renaming in edit mode, remove old entry
                if mode == "edit" and rig_name and new_name != rig_name:
                    if rig_name in self.rig_data:
                        del self.rig_data[rig_name]

                self.rig_data[new_name] = new_data
                self.save_data()
                self.load_data()

    def add_new_rig(self):
        """Opens dialog to add a new rig."""
        file_filter = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Rig File", "", file_filter)
        if not path:
            return

        path = os.path.normpath(path)
        
        # Check for duplicates
        for name, data in self.rig_data.items():
            existing_path = os.path.normpath(data.get("path", ""))
            if existing_path == path:
                QtWidgets.QMessageBox.warning(
                    self, "Duplicate", "File already exists as '{}'.".format(name)
                )
                return

        self._open_setup_dialog(mode="add", file_path=path)

    def edit_rig(self, rig_name):
        """Opens dialog to edit an existing rig."""
        if rig_name not in self.rig_data:
            return
        
        self._open_setup_dialog(
            mode="edit", 
            rig_name=rig_name, 
            rig_data=self.rig_data[rig_name]
        )

    # ---------- Persistence (Settings) ----------

    def save_windowPosition(self):
        """Save docking state and geometry."""
        try:
            if not cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, exists=True):
                return
            
            floating = cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, q=True, floating=True)
            self.settings.setValue("floating", floating)

            if floating:
                ptr = MQtUtil.findControl(self.WORKSPACE_CONTROL_NAME)
                qt_control = wrapInstance(int(ptr), QtWidgets.QWidget)
                geo = qt_control.geometry()
                tl = qt_control.mapToGlobal(geo.topLeft())
                self.settings.setValue("position", (tl.x(), tl.y()))
                self.settings.setValue("size", (geo.width(), geo.height()))
            else:
                area = cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, q=True, dockArea=True)
                self.settings.setValue("dockArea", area)
            self.settings.sync()
        except Exception as e:
            LOG.error("Error saving position: {}".format(e))

    def set_windowPosition(self):
        """Restore docking state and geometry."""
        floating = self.settings.value("floating", False)
        pos = self.settings.value("position", None)
        size = self.settings.value("size", None)

        kwargs = {"e": True, "label": self.WINDOW_TITLE, "minimumWidth": 370, "retain": False}
        
        if floating:
            kwargs["floating"] = True
        else:
            # Attempt auto-dock
            dock_target = None
            for ctl in ("ChannelBoxLayerEditor", "AttributeEditor"):
                if cmds.control(ctl, exists=True):
                    dock_target = ctl
                    break
            if dock_target:
                kwargs["tabToControl"] = [dock_target, -1]
            else:
                kwargs["floating"] = True

        try:
            cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, **kwargs)
            if floating and pos and size:
                ptr = MQtUtil.findControl(self.WORKSPACE_CONTROL_NAME)
                win = wrapInstance(int(ptr), QtWidgets.QWidget).window()
                win.setGeometry(QtCore.QRect(int(pos[0]), int(pos[1]), int(size[0]), int(size[1])))
        except Exception as e:
            LOG.error("Error restoring position: {}".format(e))

    def save_filters(self):
        try:
            self.settings.setValue("filters", self.filter_menu.get_selected())
            key, asc = self.sort_menu.get_current_sort()
            self.settings.setValue("sort_key", key)
            self.settings.setValue("sort_ascending", asc)
        except Exception as e:
            LOG.error("Error saving filters: {}".format(e))

    def load_filters(self):
        try:
            filters = self.settings.value("filters", {})
            if not filters: filters = {}
            self.filter_menu.set_selected(filters)
            
            key = self.settings.value("sort_key", "Name")
            asc_val = self.settings.value("sort_ascending", True)
            asc = (str(asc_val).lower() == 'true') if isinstance(asc_val, str) else bool(asc_val)
            self.sort_menu.set_sort(key, asc)
        except Exception as e:
            LOG.error("Error loading filters: {}".format(e))

    def dockCloseEventTriggered(self):
        self.save_windowPosition()
        self.save_filters()
        self._cleanup()

    def _cleanup(self):
        try:
            if cmds.workspaceControl(self.WORKSPACE_CONTROL_NAME, exists=True):
                cmds.deleteUI(self.WORKSPACE_CONTROL_NAME)
        except Exception: 
            pass
        self.setParent(None)
        self.deleteLater()

    @classmethod
    def showUI(cls):
        for ui in [cls.WORKSPACE_CONTROL_NAME]:
            try:
                if cmds.workspaceControl(ui, exists=True):
                    cmds.deleteUI(ui)
            except Exception: pass
        
        inst = cls(_get_maya_main_window())
        inst.show(dockable=True, retain=False)
        inst.set_windowPosition()
        return inst
