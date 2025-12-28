# -*- coding: utf-8 -*-
import os
import io
import sys
import json
import logging
from .widgets import (
    ManageRigsDialog,
    FilterMenu,
    FlowLayout,
    OpenMenu,
    RigItemWidget,
    RigSetupDialog,
    SortMenu,
)

import maya.cmds as cmds  # type: ignore
from . import utils
from . import VERSION, TOOL_TITLE

try:
    from PySide6 import QtWidgets, QtCore  # type: ignore
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtCore import Qt
    from shiboken6 import wrapInstance  # type: ignore
except ImportError:
    from PySide2 import QtWidgets, QtCore  # type: ignore
    from PySide2.QtGui import QImage, QPixmap
    from PySide2.QtCore import Qt
    from shiboken2 import wrapInstance  # type: ignore

try:
    from base64 import decodebytes
except ImportError:
    from base64 import decodestring as decodebytes

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin  # type: ignore
from maya.OpenMayaUI import MQtUtil  # type: ignore


# -------------------- Logging --------------------
LOG = logging.getLogger(TOOL_TITLE)
if not LOG.handlers:
    h = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("[{}] %(levelname)s: %(message)s".format(TOOL_TITLE))
    h.setFormatter(formatter)
    LOG.addHandler(h)
LOG.setLevel(logging.DEBUG)
LOG.propagate = False
LOG.disabled = True

# -------------------- Constants --------------------
RIGS_JSON = os.path.join(utils.MODULE_DIR, "rigs_database.json")
BLACKLIST_JSON = os.path.join(utils.MODULE_DIR, "blacklist.json")

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

    def __init__(self, rig_data, search_text, filters, referenced_set=None):
        super(SearchWorker, self).__init__()
        self.rig_data = rig_data
        self.search_text = search_text
        self.filters = filters
        self.referenced_set = referenced_set or set()
        self._is_running = True

    def run(self):
        visible_names = []
        try:
            raw_search = self.search_text.lower()
            search_tokens = raw_search.split()

            # 1. Parse query and combine with dropdown filters
            # Group prefixed search tokens by category
            text_filters = {"tags": [], "author": [], "collection": [], "link": []}
            general_terms = []

            for token in search_tokens:
                if ":" in token:
                    key, val = token.split(":", 1)
                    if key in ["t", "tag", "tags"]:
                        text_filters["tags"].append(val)
                    elif key in ["a", "auth", "author"]:
                        text_filters["author"].append(val)
                    elif key in ["c", "col", "collection"]:
                        text_filters["collection"].append(val)
                    elif key in ["l", "link"]:
                        text_filters["link"].append(val)
                    else:
                        general_terms.append(token)
                else:
                    general_terms.append(token)

            for name, data in self.rig_data.items():
                if not self._is_running:
                    return

                # Check General Context (AND search across terms) - found in NAME
                match_general = True
                if general_terms:
                    name_lower = name.lower()
                    for term in general_terms:
                        if term not in name_lower:
                            match_general = False
                            break
                if not match_general:
                    continue

                # Check Categories (Status, Collections, Tags, Author)
                # Each category is an "AND" condition against the others.
                # Within each category, dropdown selections + prefixed terms are "OR"ed.
                sel = self.filters

                # STATUS (Dropdown only)
                if sel.get("Status"):
                    statuses = sel.get("Status")
                    if "Only Available" in statuses and not data.get("exists"):
                        continue
                    if "Only Referenced" in statuses:
                        p = data.get("path")
                        norm = os.path.normpath(p).lower() if p else ""
                        if not norm or norm not in self.referenced_set:
                            continue

                # COLLECTIONS (Dropdown OR Prefix)
                target_cols = sel.get("Collections", [])
                prefix_cols = text_filters["collection"]
                if target_cols or prefix_cols:
                    rig_coll = data.get("collection")
                    # Match dropdown (exact)
                    is_dropdown_match = (rig_coll and rig_coll in target_cols) or (
                        (not rig_coll or rig_coll == "Empty") and "Empty" in target_cols
                    )
                    # Match prefix (partial)
                    is_prefix_match = False
                    if rig_coll and rig_coll != "Empty":
                        rig_coll_low = rig_coll.lower()
                        for pc in prefix_cols:
                            if pc in rig_coll_low:
                                is_prefix_match = True
                                break

                    if not (is_dropdown_match or is_prefix_match):
                        continue

                # TAGS (Dropdown OR Prefix)
                target_tags = sel.get("Tags", [])
                prefix_tags = text_filters["tags"]
                if target_tags or prefix_tags:
                    rig_tags = [t.lower() for t in data.get("tags", [])]
                    # Match dropdown (exact)
                    is_dropdown_match = bool(set(data.get("tags", [])).intersection(target_tags))
                    # Match prefix (partial)
                    is_prefix_match = False
                    for pt in prefix_tags:
                        if any(pt in rt for rt in rig_tags):
                            is_prefix_match = True
                            break

                    if not (is_dropdown_match or is_prefix_match):
                        continue

                # AUTHOR (Dropdown OR Prefix)
                target_auths = sel.get("Author", [])
                prefix_auths = text_filters["author"]
                if target_auths or prefix_auths:
                    rig_author = data.get("author")
                    # Match dropdown (exact)
                    is_dropdown_match = (rig_author and rig_author in target_auths) or (
                        (not rig_author or rig_author == "Empty") and "Empty" in target_auths
                    )
                    # Match prefix (partial)
                    is_prefix_match = False
                    if rig_author and rig_author != "Empty":
                        rig_auth_low = rig_author.lower()
                        for pa in prefix_auths:
                            if pa in rig_auth_low:
                                is_prefix_match = True
                                break

                    if not (is_dropdown_match or is_prefix_match):
                        continue

                # LINK (Prefix only)
                if text_filters["link"]:
                    rig_link = data.get("link")
                    if not rig_link or rig_link == "Empty":
                        continue
                    rig_link_low = rig_link.lower()
                    match_link = False
                    for pl in text_filters["link"]:
                        if pl in rig_link_low:
                            match_link = True
                            break
                    if not match_link:
                        continue

                visible_names.append(name)

        except Exception as e:
            LOG.error("Search worker error: {}".format(e))

        self.finished.emit(visible_names)

    def stop(self):
        self._is_running = False


class RightClickMenuButton(QtWidgets.QPushButton):
    """Button that shows its menu on both left and right click."""

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self.showMenu()
        super(RightClickMenuButton, self).mousePressEvent(event)


class LibraryUI(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    TOOL_OBJECT_NAME = TOOL_TITLE.replace(" ", "")
    WINDOW_TITLE = "{} v{}".format(TOOL_TITLE, VERSION)
    WORKSPACE_CONTROL_NAME = "{}WorkspaceControl".format(TOOL_OBJECT_NAME)

    def __init__(self, parent=None):
        parent = parent or _get_maya_main_window()
        super(LibraryUI, self).__init__(parent)
        self.setObjectName(self.TOOL_OBJECT_NAME)
        self.settings = QtCore.QSettings(TOOL_TITLE, "RigManager")

        self.rig_data = {}  # Raw data from JSON (Persistent)
        self.display_data = {}  # Runtime data with path replacements applied
        self.blacklist = []

        self._widgets_map = {}  # Cache for widgets: {name: RigItemWidget}

        # Threading
        self._search_thread = None
        self._search_worker = None

        self._build_ui()

        # Initial Load Sequence:
        # 1. Load raw data from disk
        self._load_rig_database()  # Populates self.rig_data
        self._load_blacklist()  # Populates self.blacklist

        # 2. Build filter menu structure based on loaded data
        self._update_metadata_and_menus()

        # 3. Restore filter states (now that menus exist)
        self.load_filters()
        # Also sync window position from settings if possible, or wait for show()

    def showEvent(self, event):
        super(LibraryUI, self).showEvent(event)
        # Defer heavyweight widget creation until shown to ensure correct geometry
        QtCore.QTimer.singleShot(0, lambda: self._populate_grid(trigger_search=True))

    # ---------- UI Setup ----------

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # Top Bar
        top_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(top_layout)

        # Add Button
        self.add_btn = RightClickMenuButton(self)
        self.add_btn.setIcon(utils.get_icon("add.svg"))
        self.add_btn.setFixedSize(25, 25)
        self.add_btn.setToolTip("Add new rig(s)")

        self.add_menu = OpenMenu(parent=self)
        self.add_menu.addAction(utils.get_icon("search.svg"), "Scan Folder", self.batch_add_rigs)
        self.add_menu.addAction(utils.get_icon("add.svg"), "Add Manually", self.add_new_rig)
        self.add_btn.setMenu(self.add_menu)
        self.add_btn.setIconSize(QtCore.QSize(16, 16))
        self.add_btn.setStyleSheet(
            "QPushButton { padding: 0px; margin: 0px; }"
            "QPushButton::menu-indicator { image: none; width: 0px; }"
        )

        top_layout.addWidget(self.add_btn)

        # Search
        self.search_input = QtWidgets.QLineEdit(self)
        self.search_input.setFixedHeight(25)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setPlaceholderText("Search name, tag:human, collection:M-Bundle...")
        self.search_input.textChanged.connect(self.trigger_search)
        top_layout.addWidget(self.search_input)

        # Filters
        self.filter_menu = FilterMenu("Filters", parent=self)
        self.filter_menu.setFixedHeight(25)
        self.filter_menu.setToolTip("Filter rigs by category")
        self.filter_menu.selectionChanged.connect(self.trigger_search)
        top_layout.addWidget(self.filter_menu)

        # Sort
        self.sort_menu = SortMenu("Sort", parent=self)
        self.sort_menu.setFixedHeight(25)
        self.sort_menu.setToolTip("Sort rigs")
        self.sort_menu.sortChanged.connect(self._on_sort_changed)
        top_layout.addWidget(self.sort_menu)

        # Refresh
        self.refresh_btn = QtWidgets.QPushButton("Refresh", self)
        self.refresh_btn.setIcon(utils.get_icon("refresh.svg"))
        self.refresh_btn.setFixedHeight(25)
        self.refresh_btn.setToolTip("Refresh rigs from database")
        self.refresh_btn.clicked.connect(lambda: self.load_data())
        top_layout.addWidget(self.refresh_btn)

        # Scroll Area
        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.container = QtWidgets.QWidget(self.scroll)
        self.flow_layout = FlowLayout(self.container)

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

        # Create Menu Bar
        self.create_menus()

    def create_menus(self):
        self.menu_bar = QtWidgets.QMenuBar(self)
        self.layout().setMenuBar(self.menu_bar)

        # Library Menu
        lib_menu = self.menu_bar.addMenu("Library")

        act_manage = lib_menu.addAction("Manage Rigs")
        act_manage.triggered.connect(lambda: self.manage_database(0))
        act_manage.setToolTip("Manage rigs database")

        act_settings = lib_menu.addAction("Settings")
        act_settings.triggered.connect(lambda: self.manage_database(1))
        act_settings.setToolTip("Configure application settings")

        # Help Menu
        help_menu = self.menu_bar.addMenu("Help")

        act_updates = help_menu.addAction("Check for Updates")
        act_updates.triggered.connect(self.check_updates)

        help_menu.addSeparator()

        act_about = help_menu.addAction("About")
        act_about.setIcon(utils.get_icon("info.svg"))
        act_about.triggered.connect(self.show_coffee)

    def check_updates(self):
        is_update, remote_ver = utils.check_for_updates(VERSION)

        if is_update and remote_ver:
            QtWidgets.QMessageBox.information(
                self,
                "Update Available",
                "A new version ({}) is available!\nYou are currently using v{}.\n\nPlease check the repository.".format(
                    remote_ver, VERSION
                ),
            )
        elif remote_ver:
            QtWidgets.QMessageBox.information(
                self, "Up to Date", "You are using the latest version v{}".format(VERSION)
            )
        else:
            QtWidgets.QMessageBox.warning(
                self,
                "Check Failed",
                "Could not retrieve update information.\nPlease check your internet connection.",
            )

    def show_coffee(self):
        credits_dialog = QtWidgets.QMessageBox(self)
        # credits_dialog.setWindowFlags(self.windowFlags() & Qt.FramelessWindowHint)

        base64Data = "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"
        image_64_decode = decodebytes(base64Data.encode("utf-8"))
        image = QImage()
        image.loadFromData(image_64_decode, "JPG")
        pixmap = QPixmap(image).scaledToHeight(56, Qt.SmoothTransformation)
        credits_dialog.setIconPixmap(pixmap)
        credits_dialog.setWindowTitle("About")
        credits_dialog.setText(
            "Created by @Alehaaaa<br>"
            'Website - <a href=https://alehaaaa.github.io><font color="white">alehaaaa.github.io</a><br>'
            '<a href=https://www.linkedin.com/in/alejandro-martin-407527215><font color="white">Linkedin</a> - <a href=https://www.instagram.com/alejandro_anim><font color="white">Instagram</a>'
            "<br><br>"
            "If you liked this tool,<br>"
            "you can send me some love!"
        )
        credits_dialog.setFixedSize(400, 300)
        exec_fn = getattr(credits_dialog, "exec", None) or getattr(credits_dialog, "exec_", None)
        exec_fn()

    def _show_custom_message(self, title, message, icon=None):
        """Helper to show a sleek message dialog instead of native QMessageBox."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(300, 150)
        dlg.setStyleSheet("QDialog { background-color: #333; color: #FFF; } QLabel { color: #EEE; }")

        layout = QtWidgets.QVBoxLayout(dlg)

        lbl = QtWidgets.QLabel(message, dlg)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 11pt; padding: 10px;")
        layout.addWidget(lbl)

        btn = QtWidgets.QPushButton("OK", dlg)
        btn.setCursor(QtCore.Qt.PointingHandCursor)
        btn.clicked.connect(dlg.accept)
        btn.setStyleSheet(
            "QPushButton { background-color: #555; padding: 6px; border-radius: 4px; } QPushButton:hover { background-color: #666; }"
        )

        h_layout = QtWidgets.QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(btn)
        h_layout.addStretch()

        layout.addLayout(h_layout)
        dlg.exec_()

    # ---------- Data Management ----------

    def load_data(self, restore_scroll=True):
        """
        Full Refresh: Reloads everything from disk and updates UI.
        Used by the 'Refresh' button or after major changes.
        """
        scroll_pos = 0
        if restore_scroll:
            try:
                scroll_pos = self.scroll.verticalScrollBar().value()
            except Exception:
                pass

        # 1. Load Data
        self._load_rig_database()
        self._load_blacklist()

        # 2. Update UI Metadata (Filter options)
        self._update_metadata_and_menus()
        self.load_filters()

        # 3. Populate Grid (Create widgets)
        self._populate_grid(trigger_search=True)

        # Restore scroll
        if restore_scroll and scroll_pos > 0:
            QtCore.QTimer.singleShot(10, lambda: self.scroll.verticalScrollBar().setValue(scroll_pos))

    def _load_rig_database(self):
        """Loads main database from JSON. replacements are applied to a separate runtime dict."""
        if os.path.exists(RIGS_JSON):
            try:
                with io.open(RIGS_JSON, "r", encoding="utf-8") as f:
                    self.rig_data = json.load(f)
            except Exception as e:
                LOG.error("Failed to load JSON: {}".format(e))
                self.rig_data = {}
        else:
            self.rig_data = {}

        # Create Display Data (Clone)
        self.display_data = json.loads(json.dumps(self.rig_data))

        # Apply Replacements to Display Data ONLY
        replacements = self._get_replacements()

        if replacements and self.display_data:
            for key, data in self.display_data.items():
                if "path" in data and data["path"]:
                    data["path"] = utils.apply_path_replacements(data["path"], replacements)

                if "alternatives" in data:
                    new_alts = []
                    for alt in data["alternatives"]:
                        new_alts.append(utils.apply_path_replacements(alt, replacements))
                    data["alternatives"] = new_alts

    def _get_replacements(self):
        raw_replacements = self.settings.value("path_replacements") or "[]"
        try:
            return json.loads(raw_replacements)
        except Exception:
            return []

    def _load_blacklist(self):
        if os.path.exists(BLACKLIST_JSON):
            try:
                with io.open(BLACKLIST_JSON, "r", encoding="utf-8") as f:
                    self.blacklist = json.load(f)
            except Exception as e:
                LOG.error("Failed to load blacklist: {}".format(e))
                self.blacklist = []
        else:
            self.blacklist = []

    def _update_metadata_and_menus(self):
        """Scans rig_data for unique tags/collections and updates filter menu."""
        collections = set()
        all_tags = set()
        authors = set()

        has_empty_collection = False
        has_empty_author = False

        for key, details in self.display_data.items():
            if key.startswith("_"):
                continue

            # Update existence check cheaply here
            details["exists"] = bool(os.path.exists(details.get("path", "")))

            # Collections
            val = details.get("collection")
            if val and val != "Empty":
                collections.add(val)
            else:
                has_empty_collection = True

            # Tags
            for t in details.get("tags", []):
                if t:
                    all_tags.add(t)

            # Authors
            val_auth = details.get("author")
            if val_auth and val_auth != "Empty":
                authors.add(val_auth)
            else:
                has_empty_author = True

        # Build Menu Items
        cols_sorted = sorted(list(collections))
        if has_empty_collection:
            cols_sorted = ["Empty"] + cols_sorted

        auths_sorted = sorted(list(authors))
        if has_empty_author:
            auths_sorted = ["Empty"] + auths_sorted

        self.filter_menu.set_items(
            sections={
                "Status": ["Only Available", "Only Referenced"],
                "Tags": sorted(list(all_tags)),
                "Collections": cols_sorted,
                "Author": auths_sorted,
            }
        )
        # Note: This resets the menu items (clearing checks).
        # Call load_filters() immediately after this if you want to restore state.

    def save_blacklist(self):
        """Saves current blacklist to its own JSON."""
        try:
            with io.open(BLACKLIST_JSON, "w", encoding="utf-8") as f:
                json.dump(self.blacklist, f, indent=4, ensure_ascii=False)
        except Exception as e:
            LOG.error("Failed to save blacklist: {}".format(e))

    def save_data(self):
        """Saves current rig_data to JSON."""
        try:
            with io.open(RIGS_JSON, "w", encoding="utf-8") as f:
                json.dump(self.rig_data, f, indent=4)
        except Exception as e:
            LOG.error("Failed to save JSON: {}".format(e))

    def _populate_grid(self, trigger_search=True):
        """
        Populate the grid with widgets.
        Uses a reconciliation strategy to reuse widgets and avoid UI flicker.
        """
        if not hasattr(self, "_widgets_map"):
            self._widgets_map = {}

        # 1. Remove stale widgets
        current_names = set(self.display_data.keys())
        cached_names = set(self._widgets_map.keys())
        to_remove = cached_names - current_names

        for name in to_remove:
            wid = self._widgets_map.pop(name)
            if wid:
                wid.hide()
                self.flow_layout.removeWidget(wid)
                wid.setParent(None)
                wid.deleteLater()

        # 2. Detach all remaining widgets from layout (to re-sort)
        while self.flow_layout.count():
            self.flow_layout.takeAt(0)

        # 3. Determine Sort Order
        sort_mode, ascending = self.sort_menu.get_current_sort()

        def sort_key_func(item):
            name, data = item
            val = ""
            if sort_mode == "Collection":
                val = data.get("collection")
            elif sort_mode == "Author":
                val = data.get("author")

            # Always return a tuple for consistent comparison
            if sort_mode == "Name":
                return (name.lower(), "")

            # For other modes, put Empty/None at the bottom
            if not val or val == "Empty":
                # Use a high-value character to push Empty to the bottom in ascending sort
                sort_val = "\uffff"
            else:
                sort_val = val.lower()

            return (sort_val, name.lower())

        blacklist = set(self.blacklist)
        rig_items = []
        for n, d in self.display_data.items():
            if n.startswith("_"):
                continue

            # Skip if the main path is blacklisted
            path = d.get("path")
            if path and os.path.normpath(path) in blacklist:
                continue

            rig_items.append((n, d))

        sorted_items = sorted(rig_items, key=sort_key_func, reverse=not ascending)

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
                    wid.dataChanged.connect(lambda k, v, n=name: self._on_widget_data_changed(n, k, v))
                    wid.filterRequested.connect(self.apply_single_filter)
                    wid.editRequested.connect(self.edit_rig)
                    wid.removeRequested.connect(self.remove_rig)
                    wid.refreshRequested.connect(self.load_data)
                    wid.set_exists(data["exists"])
                    self._widgets_map[name] = wid
                except Exception as e:
                    LOG.error("Failed to create widget '{}': {}".format(name, e))
                    continue

            self.flow_layout.addWidget(wid)

        if trigger_search:
            self.trigger_search(sync=False)

    # ---------- Search & Filtering ----------

    def trigger_search(self, sync=False):
        """
        Runs the search logic.
        Args:
            sync (bool): If True, runs immediately in main thread (blocking).
                         Use this during startup to ensure correct initial state.
        """
        # Cancel existing thread
        if self._search_thread:
            try:
                if self._search_thread.isRunning():
                    if self._search_worker:
                        self._search_worker.stop()
                    self._search_thread.quit()
                    self._search_thread.wait()
            except RuntimeError:
                pass

        search_text = self.search_input.text()
        filters = self.filter_menu.get_selected()

        # Save UI state immediately
        self.save_filters()

        # Get Referenced Sets to filter by usage
        referenced_set = set()
        try:
            refs = cmds.file(q=True, reference=True)
            if refs:
                for r in refs:
                    referenced_set.add(os.path.normpath(r).lower())
        except Exception:
            pass

        # Create worker
        worker = SearchWorker(self.display_data, search_text, filters, referenced_set)

        if sync:
            # Synchronous Execution
            worker.finished.connect(self._on_search_finished)
            worker.run()

        else:
            # Async Execution
            self._search_thread = QtCore.QThread()
            self._search_worker = worker  # Keep ref
            self._search_worker.moveToThread(self._search_thread)

            self._search_thread.started.connect(self._search_worker.run)
            self._search_worker.finished.connect(self._on_search_finished)
            self._search_worker.finished.connect(self._search_thread.quit)
            self._search_worker.finished.connect(self._search_worker.deleteLater)
            self._search_thread.finished.connect(self._search_thread.deleteLater)

            self._search_thread.start()

    def _on_sort_changed(self, key, ascending):
        self.settings.setValue("sort_key", key)
        self.settings.setValue("sort_ascending", ascending)
        self._populate_grid()

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

    def apply_single_filter(self, category, value):
        self.filter_menu.set_selected({category: [value]})
        self.trigger_search()

    def _on_widget_data_changed(self, name, key, value):
        """Handle data changes from widgets (image, path) safely."""
        if name in self.rig_data:
            # Update RAW data (for database)
            self.rig_data[name][key] = value
            self.save_data()

            # Update Display Data (for runtime)
            if key == "path":
                # Re-apply replacements for display
                replacements = self._get_replacements()
                new_path = utils.apply_path_replacements(value, replacements)
                # Check existence
                self.display_data[name]["path"] = new_path
                self.display_data[name]["exists"] = bool(os.path.exists(new_path))
            else:
                self.display_data[name][key] = value

            # Notify widget of the official display data state
            if name in self._widgets_map:
                try:
                    self._widgets_map[name].update_data(self.display_data[name])
                except RuntimeError:
                    pass

    # ---------- Rig Management (Add/Edit) ----------

    def _get_autocomplete_data(self):
        """Helper to gather unique collections, authors, and tags from current data."""
        collections = set()
        authors = set()
        all_tags = set()

        for name, details in self.display_data.items():
            if name.startswith("_"):
                continue
            if details.get("collection"):
                collections.add(details.get("collection"))
            if details.get("author"):
                authors.add(details.get("author"))
            if details.get("tags"):
                all_tags.update(details.get("tags"))

        return sorted(list(collections)), sorted(list(authors)), sorted(list(all_tags))

    def _open_setup_dialog(self, mode, file_path=None, rig_name=None, rig_data=None):
        """Shared logic for opening the add/edit dialog."""
        cols, auths, tags = self._get_autocomplete_data()
        existing_names = [n for n in self.rig_data.keys() if not n.startswith("_")]

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

                # Save UI state so load_data -> load_filters picks it up
                self.save_filters()
                self.load_data()
                return True
        return False

    def add_new_rig(self):
        """Opens dialog to add a new rig."""
        file_filter = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Rig File", "", file_filter)
        if not path:
            return

        path = os.path.normpath(path)

        # Check for duplicates using replaced paths
        for name, data in self.display_data.items():
            if name.startswith("_"):
                continue
            # Check main path and alternatives (already replaced in display_data)
            all_paths = [data.get("path", "")] + data.get("alternatives", [])
            norm_paths = [os.path.normpath(p) for p in all_paths if p]

            if path in norm_paths:
                # Instead of popup, highlight existing
                self._highlight_rig_by_name(name)
                return

        self._open_setup_dialog(mode="add", file_path=path)

    def batch_add_rigs(self):
        """Opens dialog to select a directory for batch adding rigs."""
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory to Scan for Rigs")
        if not path:
            return

        path = os.path.normpath(path)
        cols, auths, tags = self._get_autocomplete_data()

        dlg = ManageRigsDialog(
            directory=path,
            rig_data=self.rig_data,
            blacklist=self.blacklist,
            collections=cols,
            authors=auths,
            tags=tags,
            parent=self,
        )

        dlg.rigAdded.connect(self._on_batch_rig_added)
        dlg.blacklistChanged.connect(self._on_blacklist_changed)

        dlg.exec_()
        self.save_data()
        self.save_filters()
        self.load_data()

    def _on_batch_rig_added(self, name, data):
        """Callback from ManageRigsDialog when a rig is configured and added."""
        self.rig_data[name] = data

    def _on_blacklist_changed(self, new_blacklist):
        """Callback from ManageRigsDialog when blacklist is updated."""
        self.blacklist = new_blacklist
        self.save_blacklist()

    def manage_database(self, tab_index=0):
        """Opens the Manage Rigs dialog.

        Args:
            tab_index (int): 0 for Rigs, 1 for Settings.
        """
        cols, auths, tags = self._get_autocomplete_data()

        dlg = ManageRigsDialog(
            directory=None,
            rig_data=self.rig_data,
            blacklist=self.blacklist,
            collections=cols,
            authors=auths,
            tags=tags,
            initial_tab=tab_index,
            parent=self,
        )

        dlg.rigAdded.connect(self._on_batch_rig_added)
        dlg.blacklistChanged.connect(self._on_blacklist_changed)

        dlg.exec_()
        self.save_data()
        self.save_filters()
        self.load_data()

    def edit_rig(self, rig_name):
        """Opens dialog to edit an existing rig."""
        if rig_name not in self.rig_data:
            return

        # Keep ref to widget to close info dialog if needed
        wid = self._widgets_map.get(rig_name)

        saved = self._open_setup_dialog(mode="edit", rig_name=rig_name, rig_data=self.rig_data[rig_name])

        if saved and wid:
            try:
                wid.close_info_dialog()
            except Exception:
                pass

    def remove_rig(self, rig_name):
        """Removes a rig from the database."""
        if rig_name in self.rig_data:
            del self.rig_data[rig_name]
            self.save_data()
            self.load_data()  # Reload to refresh UI
            LOG.info("Removed rig: {}".format(rig_name))

    # ---------- Persistence (Settings) ----------

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

            if floating:
                ptr = MQtUtil.findControl(self.WORKSPACE_CONTROL_NAME)
                qt_control = wrapInstance(int(ptr), QtWidgets.QWidget)
                geo = qt_control.geometry()
                top_left_global = qt_control.mapToGlobal(geo.topLeft())

                position = (top_left_global.x(), top_left_global.y())
                size = (geo.width(), geo.height())

                self.settings.setValue("position", position)
                self.settings.setValue("size", size)

                self.settings.setValue("floating", True)
                LOG.info("Saved floating = {} position {} size {}".format(True, position, size))
            else:
                self.settings.setValue("floating", False)
                LOG.info("Saved floating = {}".format(False))

            self.settings.sync()  # Force settings to write immediately
            LOG.info("Window position saved successfully.")

        except Exception as e:
            LOG.error("Error saving window position: {}".format(e))

    def set_windowPosition(self):
        """
        Restores or initializes the dock/floating position of the workspace control.
        """
        floating = utils.setting_bool(self.settings.value("floating") or False)

        LOG.info("Restoring floating = {}".format(floating))
        position = self.settings.value("position")
        size = self.settings.value("size")

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
                if cmds.workspaceControl(ctl, exists=True):
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

    def save_filters(self):
        try:
            self.settings.setValue("search_text", self.search_input.text())
            self.settings.setValue("filters", self.filter_menu.get_selected())

            key, asc = self.sort_menu.get_current_sort()
            self.settings.setValue("sort_key", key)
            self.settings.setValue("sort_ascending", asc)
        except Exception as e:
            LOG.error("Error saving filters: {}".format(e))

    def load_filters(self):
        try:
            filters = self.settings.value("filters") or {}
            if not filters:
                filters = {}
            self.filter_menu.set_selected(filters)

            search_text = self.settings.value("search_text") or ""
            self.search_input.setText(search_text)

            key = self.settings.value("sort_key") or "Name"
            asc = utils.setting_bool(self.settings.value("sort_ascending") or True)

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
            except Exception:
                pass

        inst = cls(_get_maya_main_window())
        inst.show(dockable=True, retain=False)
        inst.set_windowPosition()
        return inst

    def _highlight_rig_by_name(self, rig_name):
        """Scrolls to and highlights a rig widget."""
        if rig_name in self._widgets_map:
            wid = self._widgets_map[rig_name]
            self.scroll.ensureWidgetVisible(wid)

            # Flash effect
            orig_style = wid.styleSheet()
            wid.setStyleSheet(".RigItemWidget { background-color: #554444; border: 2px solid #DD5555; }")

            def restore():
                try:
                    wid.setStyleSheet(orig_style)
                except Exception:
                    pass

            QtCore.QTimer.singleShot(2000, restore)
