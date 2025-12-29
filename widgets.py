import os
import subprocess
import logging
import sys
import json
import fnmatch
from maya import cmds

try:
    from PySide6 import QtWidgets, QtCore, QtGui  # type: ignore
    from PySide6.QtGui import QAction, QActionGroup  # type: ignore
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui  # type: ignore
    from PySide2.QtWidgets import QAction, QActionGroup

from . import utils
from . import TOOL_TITLE

# -------------------- Logging --------------------
LOG = logging.getLogger(TOOL_TITLE)

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


class ContextLabel(QtWidgets.QLabel):
    """A QLabel that provides a context menu to copy its text or tooltip."""

    def __init__(self, text="", is_path=False, is_link=False, parent=None):
        super(ContextLabel, self).__init__(text, parent)
        self._is_path = is_path
        self._is_link = is_link
        self.setCursor(CONTEXTUAL_CURSOR)
        if text:
            self.setToolTip(text)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        label = "Copy URL" if self._is_link else "Copy path" if self._is_path else "Copy"
        copy_act = menu.addAction(label)

        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action == copy_act:
            # Prefer tooltip as it usually holds the full un-elided text
            text_to_copy = self.toolTip() or self.text()
            QtWidgets.QApplication.clipboard().setText(text_to_copy)


class LoadingDotsWidget(QtWidgets.QLabel):
    """A standalone widget that cycles through dots (. .. ...) for loading states."""

    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super(LoadingDotsWidget, self).__init__(parent)
        self._dots_count = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._update_dots)
        self.setFixedWidth(20)  # Fixed width for 3 dots to avoid jitter
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.setStyleSheet("color: #888; margin: 0; padding: 0;")  # Explicitly remove margins/padding
        self.hide()

    def start(self):
        self._dots_count = 0
        self._update_dots()
        self._timer.start(500)
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def get_dots_text(self):
        """Returns the current dots combined with transparent spacers for layout consistency."""
        dots = "." * self._dots_count
        hidden = "." * (3 - self._dots_count)
        return "{}<span style='color:transparent;'>{}</span>".format(dots, hidden)

    def _update_dots(self):
        self.setText(self.get_dots_text())
        self._dots_count = (self._dots_count + 1) % 4


class ElidedClickableLabel(ContextLabel):
    """A label that elides text from the left and responds to click events."""

    clicked = QtCore.Signal()

    def __init__(self, text, is_path=False, is_link=False, parent=None):
        super(ElidedClickableLabel, self).__init__(text, is_path=is_path, is_link=is_link, parent=parent)
        self._full_text = text
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self.updateGeometry()
        self.update()

    def minimumSizeHint(self):
        return QtCore.QSize(10, super(ElidedClickableLabel, self).minimumSizeHint().height())

    def sizeHint(self):
        fm = self.fontMetrics()
        w = (
            fm.horizontalAdvance(self._full_text)
            if hasattr(fm, "horizontalAdvance")
            else fm.width(self._full_text)
        )
        return QtCore.QSize(w, super(ElidedClickableLabel, self).sizeHint().height())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        metrics = painter.fontMetrics()
        elided = metrics.elidedText(self._full_text, QtCore.Qt.ElideLeft, self.width())

        painter.setPen(QtGui.QColor("#74accc"))
        painter.drawText(self.rect(), self.alignment() | QtCore.Qt.AlignVCenter, elided)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super(ElidedClickableLabel, self).mousePressEvent(event)


# -------------------- Scrollable Menu --------------------


class ScrollArrowButton(QtWidgets.QWidget):
    """Custom button for hover-based scrolling in ScrollableMenu."""

    def __init__(self, arrow_type, menu):
        super(ScrollArrowButton, self).__init__(menu)
        self.arrow_type = arrow_type
        self.menu = menu
        self.setFixedHeight(15)
        self.setMouseTracking(True)
        self.hovered = False
        self.pressed = False
        self.hide()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Semi-transparent overlay background
        if self.pressed:
            bg_color = QtGui.QColor(35, 35, 35)
        elif self.hovered:
            bg_color = QtGui.QColor(65, 65, 65)
        else:
            bg_color = QtGui.QColor(45, 45, 45)
        painter.fillRect(self.rect(), bg_color)

        # Arrow
        painter.setPen(QtGui.QPen(QtGui.QColor(220, 220, 220), 1.5))
        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2.0, h / 2.0

        if self.arrow_type == QtCore.Qt.UpArrow:
            # Width: 8 (cx-4 to cx+4), Height: 4 (cy-2 to cy+2)
            painter.drawLine(QtCore.QLineF(cx - 4, cy + 2, cx, cy - 2))
            painter.drawLine(QtCore.QLineF(cx, cy - 2, cx + 4, cy + 2))
        else:
            painter.drawLine(QtCore.QLineF(cx - 4, cy - 2, cx, cy + 2))
            painter.drawLine(QtCore.QLineF(cx, cy + 2, cx + 4, cy - 2))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.pressed = True
            self.update()
        super(ScrollArrowButton, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.pressed = False
            self.update()
            vbar = self.menu._scroll_area.verticalScrollBar()
            if self.arrow_type == QtCore.Qt.UpArrow:
                vbar.setValue(0)
            else:
                vbar.setValue(vbar.maximum())
            self.menu._update_arrows()
            return
        super(ScrollArrowButton, self).mouseReleaseEvent(event)

    def enterEvent(self, event):
        self.hovered = True
        self.menu._start_scroll(-1 if self.arrow_type == QtCore.Qt.UpArrow else 1)
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.menu._stop_scroll()
        self.update()


class ScrollContainer(QtWidgets.QWidget):
    """Container that positions scroll arrows as overlays to prevent layout jiggle."""

    def __init__(self, scroll_area, up_btn, down_btn):
        super(ScrollContainer, self).__init__()
        self.scroll_area = scroll_area
        self.up_btn = up_btn
        self.down_btn = down_btn

        self.up_btn.setParent(self)
        self.down_btn.setParent(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll_area)

    def resizeEvent(self, event):
        super(ScrollContainer, self).resizeEvent(event)
        w = self.width()
        h = self.height()
        self.up_btn.setGeometry(0, 0, w, 15)
        self.down_btn.setGeometry(0, h - 15, w, 15)
        self.up_btn.raise_()
        self.down_btn.raise_()


class MenuItemWidget(QtWidgets.QWidget):
    """Custom widget representing a single checkable menu item within ScrollableMenu."""

    # Easily changeable layout values
    WIDGET_HEIGHT = 20
    CHECKBOX_SIZE = 12
    CONTENT_PADDING = 6

    EXTRA_LEFT_MARGIN = 1  # Added left margin to match look of Maya

    def __init__(self, action, menu):
        super(MenuItemWidget, self).__init__()
        self.action = action
        self.menu = menu

        self._hovered = False

        self.setFixedHeight(self.WIDGET_HEIGHT)
        self.setMouseTracking(True)

        self.action.changed.connect(self.update)
        self.action.toggled.connect(lambda _: self.update())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        h = float(self.WIDGET_HEIGHT)
        cs = float(self.CHECKBOX_SIZE)
        margin_y = (h - cs) / 2.0
        margin_x = margin_y + self.EXTRA_LEFT_MARGIN

        # Column width shifts to accommodate the extra pixel
        column_w = int(h) + self.EXTRA_LEFT_MARGIN

        # Define the two distinct areas
        checkbox_bg_rect = self.rect()
        checkbox_bg_rect.setWidth(column_w)
        text_bg_rect = self.rect().adjusted(column_w, 0, 0, 0)

        # Draw Checkbox Column Background
        painter.fillRect(checkbox_bg_rect, QtGui.QColor(64, 64, 64))

        # Draw Text Area Background
        if self._hovered:
            painter.fillRect(text_bg_rect, QtGui.QColor(82, 133, 166))
        else:
            painter.fillRect(text_bg_rect, QtGui.QColor(82, 82, 82))

        # Checkbox
        if self.action.isCheckable():
            # Square checkbox centered vertically, shifted by margin_x horizontally
            check_rect = QtCore.QRectF(margin_x, margin_y, cs, cs)
            # Always dark, borderless background
            painter.fillRect(check_rect, QtGui.QColor(43, 43, 43))

            if self.action.isChecked():
                # Draw white checkmark
                painter.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200), 1.8))

                # Proportional checkmark points for scalability
                lx = check_rect.x() + cs * 0.22
                ly = check_rect.y() + cs * 0.5
                mx = check_rect.x() + cs * 0.43
                my = check_rect.y() + cs * 0.72
                rx = check_rect.x() + cs * 0.78
                ry = check_rect.y() + cs * 0.28

                painter.drawLine(QtCore.QPointF(lx, ly), QtCore.QPointF(mx, my))
                painter.drawLine(QtCore.QPointF(mx, my), QtCore.QPointF(rx, ry))

        # Content (Icon + Text) starts after the checkbox column + padding
        text_offset = column_w + self.CONTENT_PADDING

        # Icon
        icon = self.action.icon()
        if not icon.isNull():
            icon_size = 16
            icon_y = (h - icon_size) / 2.0
            icon.paint(painter, QtCore.QRect(int(text_offset), int(icon_y), icon_size, icon_size))
            text_offset += 24

        # Text
        text_color = QtGui.QColor(238, 238, 238)
        painter.setPen(text_color)
        font = self.action.font()
        painter.setFont(font)

        # Use a safe margin at the right
        text_rect = self.rect().adjusted(int(text_offset), 0, -10, 0)
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            self.action.text(),
        )

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mouseReleaseEvent(self, event):
        if self.action.isCheckable():
            self.action.setChecked(not self.action.isChecked())
        else:
            self.action.trigger()
            self.menu.close()

    def sizeHint(self):
        fm = self.fontMetrics()
        text_w = (
            fm.horizontalAdvance(self.action.text())
            if hasattr(fm, "horizontalAdvance")
            else fm.width(self.action.text())
        )

        # Dynamic width: Checkbox Block (H+1) + Padding + (Icon Area if exists) + Text Width + Buffer
        offset = self.WIDGET_HEIGHT + 1 + self.CONTENT_PADDING
        if not self.action.icon().isNull():
            offset += 24

        return QtCore.QSize(text_w + int(offset) + 20, self.WIDGET_HEIGHT)


class ScrollableMenu(OpenMenu):
    """
    A QMenu that embeds a QScrollArea with hover-based scrolling arrows.
    Used for long filter lists to avoid multiple columns.
    """

    def __init__(self, title=None, parent=None):
        super(ScrollableMenu, self).__init__(title, parent)
        self._added_actions = []

        # Remove QMenu internal padding and ensure full-width layout
        self.setStyleSheet("QMenu { background: #404040; padding: 0px; }")
        self.setContentsMargins(0, 0, 0, 0)

        self._scroll_area = QtWidgets.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self._scroll_area.setContentsMargins(0, 0, 0, 0)
        self._scroll_area.setMaximumHeight(600)

        # Handle mouse wheel visibility
        self._scroll_area.verticalScrollBar().valueChanged.connect(lambda _: self._update_arrows())

        self._content_widget = QtWidgets.QWidget()
        self._content_layout = QtWidgets.QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._scroll_area.setWidget(self._content_widget)

        self._up_btn = ScrollArrowButton(QtCore.Qt.UpArrow, self)
        self._down_btn = ScrollArrowButton(QtCore.Qt.DownArrow, self)

        self._container = ScrollContainer(self._scroll_area, self._up_btn, self._down_btn)

        self._main_action = QtWidgets.QWidgetAction(self)
        self._main_action.setDefaultWidget(self._container)
        super(ScrollableMenu, self).addAction(self._main_action)

        self._scroll_timer = QtCore.QTimer(self)
        self._scroll_timer.timeout.connect(self._do_scroll)
        self._scroll_speed = 0

    def _start_scroll(self, direction):
        self._scroll_speed = direction * 10
        self._scroll_timer.start(16)

    def _stop_scroll(self):
        self._scroll_timer.stop()

    def _do_scroll(self):
        vbar = self._scroll_area.verticalScrollBar()
        vbar.setValue(vbar.value() + self._scroll_speed)
        self._update_arrows()

    def _update_arrows(self):
        vbar = self._scroll_area.verticalScrollBar()
        self._up_btn.setVisible(vbar.value() > 0)
        self._down_btn.setVisible(vbar.value() < vbar.maximum())

    def addAction(self, action):
        if isinstance(action, str):
            action = QAction(action, self)

        if not isinstance(action, QtWidgets.QWidgetAction):
            self._added_actions.append(action)
            wid = MenuItemWidget(action, self)
            self._content_layout.addWidget(wid)
            QtCore.QTimer.singleShot(0, self._update_arrows)
            return action
        return super(ScrollableMenu, self).addAction(action)

    def addSection(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setFixedHeight(MenuItemWidget.WIDGET_HEIGHT + MenuItemWidget.EXTRA_LEFT_MARGIN)
        lbl.setStyleSheet(
            "font-weight: bold; "
            "background-color: #353535; "  # Darker than menu's #444
            "color: #9f9f9f; "
            "padding-left: 10px;"
        )
        self._content_layout.addWidget(lbl)
        return lbl

    def addSeparator(self):
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        line.setStyleSheet("background-color: #444; margin: 2px 0px; max-height: 1px;")
        self._content_layout.addWidget(line)

    def clear(self):
        self._added_actions = []
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._update_arrows()

    def actions(self):
        return self._added_actions

    def sizeHint(self):
        # Calculate Height based on content alone (arrows are overlayed)
        self._content_layout.activate()
        content_h = self._content_widget.sizeHint().height()
        h = min(content_h, self._scroll_area.maximumHeight())

        # Calculate Width: Match parent button width OR content width
        w = 200
        if self.parentWidget():
            w = max(w, self.parentWidget().width())

        # Check content width via action items
        content_w = self._content_widget.sizeHint().width()
        w = max(w, content_w + 10)

        return QtCore.QSize(w, h)

    def showEvent(self, event):
        # Calculate and enforce size
        hint = self.sizeHint()
        self._container.setFixedSize(hint)
        self.setFixedSize(hint)

        super(ScrollableMenu, self).showEvent(event)

        # Update arrows immediately
        QtCore.QTimer.singleShot(0, self._update_arrows)


class FilterMenu(QtWidgets.QPushButton):
    """Button with a checkable menu for filtering."""

    selectionChanged = QtCore.Signal()

    def __init__(self, title, parent=None):
        super(FilterMenu, self).__init__(title, parent)
        self.menu = ScrollableMenu(parent=self)
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
                    action = QAction(item, self.menu)
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
        self.menu = OpenMenu(parent=self)
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
        self.image_lbl = ClickableLabel(self)
        self.image_lbl.clicked.connect(self.change_image)
        layout.addWidget(self.image_lbl)
        self.update_image_display()

        # Name
        self.name_lbl = QtWidgets.QLabel(self.name, self)
        self.name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.name_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.name_lbl)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.action_btn = QtWidgets.QPushButton("ADD", self)
        self.action_btn.setMinimumHeight(25)
        btn_layout.addWidget(self.action_btn, 2)

        self.info_btn = QtWidgets.QPushButton(self)
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
            self,
            "Locate Rig File",
            directory,
            "Maya Files (*.ma *.mb);;All Files (*.*)",
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
                utils.LOG.info("Referenced rig: {}".format(self.name))
            except Exception as e:
                utils.LOG.error("Error referencing: {}".format(e))
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
                utils.LOG.info("Removed reference: {}".format(self.name))
            except Exception as e:
                utils.LOG.error("Remove failed: {}".format(e))
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


class PillWidget(QtWidgets.QFrame):
    """A pill-shaped widget representing a tag."""

    clicked = QtCore.Signal()
    close_clicked = QtCore.Signal()

    def __init__(self, text, close_btn=False, parent=None):
        super(PillWidget, self).__init__(parent)
        self.setObjectName("TagPill")
        self.setFixedHeight(24)

        style = """
            #TagPill {
                background-color: #444;
                border: 1px solid #7d7d7d;
                border-radius: 12px;
                color: #aaa;
            }
        """

        if not close_btn:
            self.setCursor(QtCore.Qt.PointingHandCursor)
            style += """
                #TagPill:hover {
                    background-color: #555;
                    border-color: #949494;
                }
                #TagPill:pressed {
                    background-color: #222;
                }
            """

        self.setStyleSheet(style)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 2 if close_btn else 5, 0)
        layout.setSpacing(0)

        label = QtWidgets.QLabel(text)
        layout.addWidget(label)

        if close_btn:
            self.close_btn = QtWidgets.QPushButton()
            self.close_btn.setIcon(utils.get_icon("remove.svg"))
            self.close_btn.setIconSize(QtCore.QSize(12, 12))
            self.close_btn.setFixedSize(18, 18)
            self.close_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.close_btn.setStyleSheet("""
                QPushButton { color: #aaa; border-radius: 9px; }
                QPushButton:hover { background-color: #666; color: #d6d6d6; }
            """)
            self.close_btn.clicked.connect(self.close_clicked.emit)
            layout.addWidget(self.close_btn)

    def mousePressEvent(self, event):
        if hasattr(self, "close_btn"):
            return
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super(PillWidget, self).mousePressEvent(event)


class TagFlowWidget(QtWidgets.QWidget):
    """A wrapper for FlowLayout specialized for displaying tag pills."""

    def __init__(self, parent=None):
        super(TagFlowWidget, self).__init__(parent)
        self.setLayout(FlowLayout(margin=0, hSpacing=4, vSpacing=4))
        # Expansion policy matches TagEditorWidget to ensure it fills available width
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

    def add_tag(self, text, callback):
        pill = PillWidget(text)
        pill.clicked.connect(callback)
        self.layout().addWidget(pill)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.layout().heightForWidth(width)

    def sizeHint(self):
        # Return a sensible default width; height is determined by heightForWidth
        w = self.width()
        if w <= 0:
            return (
                self.layout().totalSizeHint()
                if hasattr(self.layout(), "totalSizeHint")
                else QtCore.QSize(100, 24)
            )
        return QtCore.QSize(w, self.heightForWidth(w))

    def resizeEvent(self, event):
        super(TagFlowWidget, self).resizeEvent(event)
        # Force a geometry update so the parent layout (QFormLayout) re-queries the height
        self.updateGeometry()


class TagEditorWidget(QtWidgets.QWidget):
    """Widget for editing tags with visual pills."""

    tagsChanged = QtCore.Signal(list)

    def __init__(self, tags=None, parent=None):
        super(TagEditorWidget, self).__init__(parent)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.all_tags = sorted(list(tags)) if tags else []
        self.current_tags = []

        self.setLayout(FlowLayout(margin=0, hSpacing=4, vSpacing=4))

        # Input Field
        self.input_line = QtWidgets.QLineEdit(self)
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
        return super(TagEditorWidget, self).eventFilter(source, event)

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
        self.tagsChanged.emit(list(self.current_tags))

        # Defer clearing to handle QCompleter's default behavior which might restore text
        QtCore.QTimer.singleShot(0, self._post_add_cleanup)

    def _post_add_cleanup(self):
        self.input_line.clear()
        self.input_line.setFocus()

    def remove_tag(self, text):
        if text in self.current_tags:
            self.current_tags.remove(text)
            self._refresh_ui()
            self.tagsChanged.emit(list(self.current_tags))

    def _create_pill_widget(self, text):
        pill = PillWidget(text, close_btn=True, parent=self)
        pill.close_clicked.connect(lambda checked=False, t=text: self.remove_tag(t))

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


class InfoDialog(QtWidgets.QDialog):
    """Dialog showing detailed metadata for a rig."""

    filterRequested = QtCore.Signal(str, str)
    editRequested = QtCore.Signal()

    def __init__(self, name, data, parent=None):
        super(InfoDialog, self).__init__(parent)
        self.data = data
        self.name = name

        self._filter_tmpl = '<a href="{}" style="color: LightGray;">{}</a>'

        self._build_ui()
        self.setWindowTitle(name)
        self.resize(280, 400)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self.image_lbl = QtWidgets.QLabel(self)
        self.image_lbl.setFixedSize(200, 200)
        self.image_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.image_lbl.setStyleSheet("background-color: #222; border: 1px solid #444;")

        name = self.data.get("image") or utils.format_name(self.name) + ".jpg"
        path = os.path.join(utils.IMAGES_DIR, name)

        if name and os.path.exists(path):
            pix = QtGui.QPixmap(path)
            self.image_lbl.setPixmap(
                pix.scaled(self.image_lbl.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            )
        else:
            self.image_lbl.setText("No Image")

        layout.addWidget(self.image_lbl, 0, QtCore.Qt.AlignHCenter)

        name_lbl = QtWidgets.QLabel(self.name, self)
        name_lbl.setStyleSheet("font-weight: bold; font-size: 12pt;")
        name_lbl.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(name_lbl)

        self.form_layout = QtWidgets.QFormLayout()
        self.form_layout.setLabelAlignment(QtCore.Qt.AlignRight)

        self._add_row("Author", self.data.get("author"), filter_cat="Author")
        self._add_row("Link", self.data.get("link"), is_link=True)
        self._add_row("Collection", self.data.get("collection"), filter_cat="Collections")
        self._add_row("Tags", self.data.get("tags", []), filter_cat="Tags")
        self._add_row("Path", self.data.get("path"), is_path=True)

        alts = self.data.get("alternatives", [])
        if alts:
            alt_names = [os.path.basename(p) for p in alts if p]
            if alt_names:
                alt_txt = "\n".join(alt_names)
                alt_lbl = QtWidgets.QLabel(alt_txt)
                alt_lbl.setStyleSheet("color: #777;")
                alt_lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
                alt_lbl.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
                self.form_layout.addRow("Alternatives:", alt_lbl)

                # Align title label to top
                title_lbl = self.form_layout.labelForField(alt_lbl)
                if title_lbl:
                    title_lbl.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
                    title_lbl.setContentsMargins(0, 1, 0, 0)

        layout.addLayout(self.form_layout)
        layout.addStretch()

        btn_layout = QtWidgets.QHBoxLayout()
        edit_btn = QtWidgets.QPushButton("Edit", self)
        edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(edit_btn)

        close_btn = QtWidgets.QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _add_row(self, label, value, is_link=False, is_path=False, filter_cat=None):
        """Helper to add formatted rows to form layout."""
        if not value and not filter_cat:
            value = "Empty"

        # 1. Tags (List)
        if filter_cat == "Tags" and isinstance(value, list):
            if not value:
                lbl = QtWidgets.QLabel("Empty")
                lbl.setStyleSheet("color: #888; font-style: italic;")
                self.form_layout.addRow(label + ":", lbl)
                return

            container = TagFlowWidget()
            for tag in value:
                # Capture tag for lambda
                def callback(checked=False, t=tag):
                    return self._emit_filter("Tags", t)

                container.add_tag(tag, callback)

            self.form_layout.addRow(label + ":", container)
            return

        # 2. Path or Link -> ElidedClickableLabel
        if (is_link or is_path) and value != "Empty":
            elided_lbl = ElidedClickableLabel(value, is_path=is_path, is_link=is_link)
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
        lbl.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        lbl.setWordWrap(True)

        if filter_cat:
            # Collection/Author
            disp = value or "Empty"
            filt = value or "Empty"
            if disp == "Empty":
                disp = "<i>Empty</i>"

            lbl.setText(self._filter_tmpl.format(filt, disp))
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
        is_alternative=False,
        parent=None,
    ):
        super(RigSetupDialog, self).__init__(parent)
        self.mode = mode
        self.rig_name = rig_name
        self.rig_data = rig_data or {}
        self.is_alternative = is_alternative
        if self.is_alternative:
            # If editing an alternative, we don't want to show the owner's metadata
            self.rig_data = {}
        self.collections = list(collections)
        self.authors = list(authors)
        self.tags = list(tags)
        self.existing_names = existing_names

        # Capture alternatives for management
        self.current_alts = list(self.rig_data.get("alternatives", []))

        self.file_path = file_path or self.rig_data.get("path", "")
        self.image_path = ""
        self.result_data = None

        self.setWindowTitle("Edit Rig" if mode == "edit" else "Add New Rig")
        self.resize(320, 520)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # Image
        self.image_lbl = QtWidgets.QLabel("No Image\n(Click to set)", self)
        self.image_lbl.setStyleSheet(
            "QLabel {background-color: #222; border: 1px solid #555; border-radius: 5px;}"
        )
        self.image_lbl.setCursor(QtCore.Qt.PointingHandCursor)
        self.image_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.image_lbl.setFixedSize(150, 150)
        self.image_lbl.setToolTip("Click to set image")
        self.image_lbl.mousePressEvent = self.on_image_click

        # Load existing image
        cur_img = self.rig_data.get("image")
        if cur_img:
            p = os.path.join(utils.IMAGES_DIR, cur_img)
            if os.path.exists(p):
                self.image_lbl.setText("")
                # Load and crop
                img = QtGui.QImage(p)
                img = utils.crop_image_to_square(img)
                pix = QtGui.QPixmap.fromImage(img).scaled(
                    150, 150, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation
                )
                self.image_lbl.setPixmap(pix)

        layout.addWidget(self.image_lbl, 0, QtCore.Qt.AlignHCenter)

        # Form
        self.form_layout = QtWidgets.QFormLayout()

        # Name
        self.name_input = QtWidgets.QLineEdit(self)
        if self.mode == "edit" and not self.is_alternative:
            self.name_input.setText(self.rig_name)
        else:
            self.name_input.setText(os.path.splitext(os.path.basename(self.file_path))[0])
        self.name_input.textChanged.connect(self.validate_name)
        self.form_layout.addRow("Name:", self.name_input)

        # Tags
        orig_tags = self.rig_data.get("tags", [])
        # Ensure orig_tags is a list
        if not isinstance(orig_tags, list):
            orig_tags = [t.strip() for t in str(orig_tags).split(",") if t.strip()]

        self.tags_input = TagEditorWidget(self.tags, parent=self)
        self.tags_input.setTags(orig_tags)
        self.form_layout.addRow("Tags:", self.tags_input)

        # Collection
        self.coll_input = QtWidgets.QLineEdit(self)
        if self.collections:
            comp = QtWidgets.QCompleter(self.collections)
            comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.coll_input.setCompleter(comp)
        coll_val = self.rig_data.get("collection") or ""
        self.coll_input.setText("" if coll_val == "Empty" else coll_val)
        self.form_layout.addRow("Collection:", self.coll_input)

        # Author
        self.auth_input = QtWidgets.QLineEdit(self)
        if self.authors:
            comp = QtWidgets.QCompleter(self.authors)
            comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.auth_input.setCompleter(comp)
        auth_val = self.rig_data.get("author") or ""
        self.auth_input.setText("" if auth_val == "Empty" else auth_val)
        self.form_layout.addRow("Author:", self.auth_input)

        # Link
        self.link_input = QtWidgets.QLineEdit(self)
        link_val = self.rig_data.get("link") or ""
        self.link_input.setText("" if link_val == "Empty" else link_val)
        self.form_layout.addRow("Link:", self.link_input)

        # Path
        lay_path = QtWidgets.QHBoxLayout()
        self.path_input = QtWidgets.QLineEdit(self)
        self.path_input.setText(self.file_path)
        self.path_input.setReadOnly(True)
        self.path_input.setStyleSheet("color: #888; background: rgba(0,0,0,0.05);")
        lay_path.addWidget(self.path_input)

        self.path_lock_btn = QtWidgets.QPushButton()
        self.path_lock_btn.setIcon(utils.get_icon("edit.svg"))
        self.path_lock_btn.setFlat(True)
        self.path_lock_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.path_lock_btn.setFixedSize(24, 24)
        self.path_lock_btn.setCheckable(True)
        self.path_lock_btn.setToolTip("Unlock path editing")
        self.path_lock_btn.toggled.connect(self._on_path_lock_toggled)
        lay_path.addWidget(self.path_lock_btn)

        self.form_layout.addRow("Path:", lay_path)

        # Alternatives Management
        self.alts_group = QtWidgets.QWidget()
        self.alts_lay = QtWidgets.QVBoxLayout(self.alts_group)
        self.alts_lay.setContentsMargins(0, 3, 0, 0)  # Small top margin to align with label
        self.alts_lay.setSpacing(4)

        self.form_layout.addRow("Alternatives:", self.alts_group)
        # Align label to top
        lbl = self.form_layout.labelForField(self.alts_group)
        if lbl:
            lbl.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
            lbl.setContentsMargins(0, 3, 0, 0)

        self._refresh_alts_ui()

        layout.addLayout(self.form_layout)
        layout.addStretch()

        # Footer Buttons
        btns = QtWidgets.QHBoxLayout()

        # Is Alternative Checkbox
        self.alt_checkbox = QtWidgets.QCheckBox("Is Alternative", self)
        self.alt_checkbox.setToolTip("Mark this file as an alternative version of another rig")
        self.alt_checkbox.toggled.connect(self._on_alt_toggled)

        # Target Rig Selection (for alternatives)
        self.target_rig_layout = QtWidgets.QHBoxLayout()
        self.target_rig_lbl = QtWidgets.QLabel("Target Rig:")
        self.target_rig_combo = QtWidgets.QComboBox()
        self.target_rig_combo.setEditable(True)
        self.target_rig_combo.addItems(sorted(self.existing_names))
        comp = QtWidgets.QCompleter(self.existing_names)
        comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        comp.setFilterMode(QtCore.Qt.MatchContains)
        self.target_rig_combo.setCompleter(comp)

        self.target_rig_layout.addWidget(self.target_rig_lbl)
        self.target_rig_layout.addWidget(self.target_rig_combo, 1)

        # Initially hide target selection
        self.target_rig_lbl.setVisible(False)
        self.target_rig_combo.setVisible(False)

        btns.addWidget(self.alt_checkbox)
        btns.addStretch()

        self.ok_btn = QtWidgets.QPushButton("Save" if self.mode == "edit" else "Add", self)
        self.ok_btn.clicked.connect(self.accept_data)
        btns.addWidget(self.ok_btn)

        cancel = QtWidgets.QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        layout.addLayout(self.target_rig_layout)
        layout.addLayout(btns)

        # Handle initial state if editing an alternative
        if self.is_alternative or self.rig_data.get("_is_alternative", False):
            self.alt_checkbox.setChecked(True)
            if self.rig_name:
                idx = self.target_rig_combo.findText(self.rig_name)
                if idx != -1:
                    self.target_rig_combo.setCurrentIndex(idx)
                else:
                    self.target_rig_combo.setCurrentText(self.rig_name)

        self.validate_name()

    def _on_path_lock_toggled(self, checked):
        """Toggles the read-only state of the path input."""
        self.path_input.setReadOnly(not checked)
        if checked:
            self.path_input.setStyleSheet("")
            self.path_lock_btn.setToolTip("Lock path editing")
        else:
            self.path_input.setStyleSheet("color: #888; background: rgba(0,0,0,0.05);")
            self.path_lock_btn.setToolTip("Unlock path editing")

    def _on_alt_toggled(self, checked):
        """Disables/Enables fields based on alternative status."""
        self.alts_group.setVisible(not checked)
        # Find the label buddy in form layout to hide it too
        label = self.form_layout.labelForField(self.alts_group)
        if label:
            label.setVisible(not checked)

        # Disable all main fields
        self.name_input.setEnabled(not checked)
        self.tags_input.setEnabled(not checked)
        self.coll_input.setEnabled(not checked)
        self.auth_input.setEnabled(not checked)
        self.link_input.setEnabled(not checked)
        self.image_lbl.setEnabled(not checked)
        self.image_lbl.setCursor(QtCore.Qt.ArrowCursor if checked else QtCore.Qt.PointingHandCursor)

        # Show/Hide target rig selection
        self.target_rig_lbl.setVisible(checked)
        self.target_rig_combo.setVisible(checked)

        if checked:
            self.ok_btn.setEnabled(True)
            self.ok_btn.setToolTip("")
        else:
            self.validate_name()

    def on_image_click(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.webp)"
            )
            if path:
                self.image_path = path
                img = QtGui.QImage(path)
                img = utils.crop_image_to_square(img)
                pix = QtGui.QPixmap.fromImage(img).scaled(
                    150, 150, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation
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
            msg = "Name already exists"

        self.ok_btn.setEnabled(valid)
        self.ok_btn.setToolTip(msg)

    def _refresh_alts_ui(self):
        """Clears and repopulates the alternatives list in the UI."""
        # Clear layout
        while self.alts_lay.count():
            child = self.alts_lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.current_alts:
            lbl = QtWidgets.QLabel("<i>None</i>")
            lbl.setStyleSheet("color: #777;")
            self.alts_lay.addWidget(lbl)
            return

        for alt_p in self.current_alts:
            wid = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(wid)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)

            name = os.path.basename(alt_p)
            lbl = QtWidgets.QLabel(name)
            lbl.setToolTip(alt_p)
            lbl.setStyleSheet("color: #777; font-size: 9pt;")
            lay.addWidget(lbl, 1)

            btn = QtWidgets.QPushButton("×")
            btn.setFixedSize(18, 18)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setToolTip("Remove reference to this alternative")
            btn.setStyleSheet("""
                QPushButton { border: none; background: transparent; color: #aaa; font-weight: bold; font-size: 11pt; border-radius: 9px; padding-bottom: 2px; }
                QPushButton:hover { background-color: #555; color: #eee; }
            """)
            btn.clicked.connect(lambda checked=False, p=alt_p: self._remove_alt(p))
            lay.addWidget(btn)

            self.alts_lay.addWidget(wid)

    def _remove_alt(self, path):
        if path in self.current_alts:
            self.current_alts.remove(path)
            self._refresh_alts_ui()

    def accept_data(self):
        is_alt = self.alt_checkbox.isChecked()

        if is_alt:
            target_rig = self.target_rig_combo.currentText().strip()
            if not target_rig:
                QtWidgets.QMessageBox.warning(self, "Invalid Selection", "Please select a target rig.")
                return

            if target_rig not in self.existing_names:
                QtWidgets.QMessageBox.warning(
                    self, "Invalid Selection", "'{}' does not exist in the database.".format(target_rig)
                )
                return

            # Warning if converting main rig to alternative
            if self.mode == "edit" and self.rig_name and not self.is_alternative:
                msg = (
                    "You are converting the rig '{}' into an alternative.\n\n"
                    "The metadata (tags, collection, author) for this rig will be removed "
                    "from the database, and this path will be merged into '{}'.\n\n"
                    "This action cannot be undone. Do you want to continue?"
                ).format(self.rig_name, target_rig)

                res = QtWidgets.QMessageBox.warning(
                    self, "Convert to Alternative", msg, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if res == QtWidgets.QMessageBox.No:
                    return

            path = self.path_input.text().strip()
            self.result_data = {
                "name": target_rig,
                "is_alternative": True,
                "old_name": self.rig_name if self.mode == "edit" else None,
                "data": {"path": path},
            }
            self.accept()
            return

        name = self.name_input.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Name", "Please enter a rig name.")
            return

        # Ensure unique name
        final_name = name
        is_rename = self.mode == "edit" and name != self.rig_name
        is_new = self.mode == "add"

        if is_new or (
            is_rename and name in self.existing_names
        ):  # Only check for uniqueness if it's a new rig or a rename to an existing name
            counter = 2
            temp_name = name
            while temp_name in self.existing_names and (self.mode != "edit" or temp_name != self.rig_name):
                temp_name = "{} {}".format(name, counter)
                counter += 1
            final_name = temp_name
        elif self.mode == "edit" and name == self.rig_name:
            final_name = name  # If editing and name hasn't changed, no need to make it unique

        tags = self.tags_input.getTags()

        # Image handling
        img_name = self.rig_data.get("image", "")
        if self.image_path and os.path.exists(self.image_path):
            res = utils.save_image_local(self.image_path, final_name)
            if res:
                img_name = res

        path = self.path_input.text().strip()
        self.result_data = {
            "name": final_name,
            "is_alternative": False,
            "data": {
                "path": path,
                "image": img_name,
                "tags": tags,  # Do not force to "Empty" string if empty list, keep list
                "collection": self.coll_input.text().strip() or "Empty",
                "author": self.auth_input.text().strip() or "Empty",
                "link": self.link_input.text().strip() or "Empty",
                "alternatives": self.current_alts,
            },
        }
        self.accept()


# -------------------- Batch Add / Scanner --------------------


class AIWorker(QtCore.QThread):
    """Background thread to query AI API for rig tags."""

    finished = QtCore.Signal(dict)  # Returns dict of {filename: metadata}
    error = QtCore.Signal(str)  # Returns error message

    def __init__(self, endpoint, model, api_key, file_paths, custom_url=None, parent=None):
        super(AIWorker, self).__init__(parent)
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.file_paths = file_paths
        self.custom_url = custom_url

    def run(self):
        try:
            json_str, error = utils.query_ai(
                self.endpoint, self.model, self.api_key, self.file_paths, self.custom_url
            )
            if json_str:
                data = json.loads(json_str)
                self.finished.emit(data)
            elif error:
                self.error.emit(error)
            else:
                self.finished.emit({})
        except Exception as e:
            utils.LOG.error("AI Worker Error: {}".format(e))
            self.error.emit(str(e))


class ScannerWorker(QtCore.QThread):
    """Background thread to scan for Maya files and categorize them."""

    fileDiscovered = QtCore.Signal(str, str)  # path, category: 'new', 'exists', 'blacklisted'
    finished = QtCore.Signal(bool)

    def __init__(self, directory, existing_paths, blacklist, blocked_dirs=None, parent=None):
        super(ScannerWorker, self).__init__(parent)
        self.directory = directory
        self.existing_paths = existing_paths  # Set of normalized paths
        self.blacklist = blacklist  # Set/List of normalized paths
        self.blocked_dirs = blocked_dirs or [".", ".anim"]
        self._is_running = True

    def _is_blocked(self, name):
        """Helper to check if a directory name matches any blocked patterns."""
        if not name or name == "__pycache__":
            return True
        return any(b and fnmatch.fnmatch(name, b) for b in self.blocked_dirs)

    def run(self):
        any_new = False
        try:
            for root, dirs, files in os.walk(self.directory):
                if not self._is_running:
                    break

                root_name = os.path.basename(root)
                
                # Skip files inside blocked folders (unless it's the very first folder scanned)
                if root != self.directory and self._is_blocked(root_name):
                    dirs[:] = [] 
                    continue

                # Prune subdirectories before they are visited
                dirs[:] = [d for d in dirs if not self._is_blocked(d)]
                dirs.sort() 

                # Process files in current root
                files.sort()
                for f in files:
                    if not self._is_running:
                        break
                    if f.lower().endswith((".ma", ".mb")):
                        raw_path = os.path.join(root, f)
                        path = utils.normpath_posix_keep_trailing(raw_path)
                        # Check against sets using normalized path
                        lookup_path = path if sys.platform != "win32" else path.lower()
                        if lookup_path in self.blacklist:
                            self.fileDiscovered.emit(path, "blacklisted")
                        elif lookup_path in self.existing_paths:
                            self.fileDiscovered.emit(path, "exists")
                        else:
                            self.fileDiscovered.emit(path, "new")
                            any_new = True
        except Exception as e:
            utils.LOG.error("Scanner Worker Error: {}".format(e))
        finally:
            self.finished.emit(any_new)

    def stop(self):
        self._is_running = False


class ModelComboBox(QtWidgets.QComboBox):
    """Combobox that emits a signal the first time its popup is shown and waits for data."""

    firstShowPopup = QtCore.Signal()

    def __init__(self, parent=None):
        super(ModelComboBox, self).__init__(parent)
        self._has_fetched = False
        self._is_fetching = False
        self._show_after_fetch = False

    def showPopup(self):
        if not self._has_fetched:
            self._show_after_fetch = True
            if not self._is_fetching:
                self._is_fetching = True
                self.firstShowPopup.emit()
            return  # Block opening until data is ready

        super(ModelComboBox, self).showPopup()

    def mark_fetched(self):
        """Called by owner when models are loaded and items are added."""
        self._has_fetched = True
        self._is_fetching = False
        if self._show_after_fetch:
            self._show_after_fetch = False
            # Defer slightly to ensure UI is ready
            QtCore.QTimer.singleShot(10, self.showPopup)

    def reset_fetch_state(self):
        """Resets the state, usually called when changing endpoints."""
        self._has_fetched = False
        self._is_fetching = False
        self._show_after_fetch = False


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
        self.setSpacing(0)
        self.setMouseTracking(True)
        # Verify drag is enabled
        self.setDragEnabled(True)
        self.setAcceptDrops(True)

        # Smooth scrolling
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(10)

    def dropEvent(self, event):
        super(ReplacementListWidget, self).dropEvent(event)
        self.orderChanged.emit()

    def sizeHint(self):
        # Request a precise height to fit items, capped at 400px
        if self.count() == 0:
            return QtCore.QSize(super(ReplacementListWidget, self).sizeHint().width(), 100)
        h = sum(self.sizeHintForRow(i) for i in range(self.count()))
        # add a small buffer for borders
        return QtCore.QSize(super(ReplacementListWidget, self).sizeHint().width(), min(400, h + 4))

    def minimumSizeHint(self):
        return QtCore.QSize(100, 100)


class ManageRigsSeparatorWidget(QtWidgets.QWidget):
    """A horizontal line with text for sectioning."""

    def __init__(self, text, parent=None):
        super(ManageRigsSeparatorWidget, self).__init__(parent)
        self.setObjectName("section_separator")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 22, 0, 8)
        lay.setSpacing(10)
        lay.setAlignment(QtCore.Qt.AlignVCenter)

        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet("color: #a1a1a1; font-weight: bold; font-size: 11px;")
        lay.addWidget(lbl)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Plain)
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #666; border: none;")
        lay.addWidget(line, 1)


class ManageRigsItemWidget(QtWidgets.QFrame):
    """Horizontal widget for a discovered file in the scanner list."""

    editRequested = QtCore.Signal(str)
    blacklistRequested = QtCore.Signal(str)
    whitelistRequested = QtCore.Signal(str)
    removeRequested = QtCore.Signal(str)

    def __init__(self, path, category, is_found=True, parent=None):
        super(ManageRigsItemWidget, self).__init__(parent)
        self.setObjectName("ManageRigsItemWidget")
        self.path = path  # Display path (replaced)
        self.category = category  # 'new', 'exists', 'blacklisted'

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)

        # Path Label (Elided)
        self.path_lbl = QtWidgets.QLabel(path, self)
        self.path_lbl.setObjectName("scanner_path_label")
        self.path_lbl.setToolTip(path)
        self.path_lbl.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self._is_found = is_found
        self._last_rich_text = ""
        layout.addWidget(self.path_lbl, 1)

        # Buttons Container
        self.btn_layout = QtWidgets.QHBoxLayout()
        self.btn_layout.setSpacing(4)
        layout.addLayout(self.btn_layout)

        # 1. Edit/Add Button
        self.edit_btn = QtWidgets.QPushButton()
        self.edit_btn.setFixedSize(22, 22)
        self.edit_btn.clicked.connect(lambda: self.editRequested.emit(self.path))
        self.btn_layout.addWidget(self.edit_btn)

        # 2. Blacklist Button
        self.blacklist_btn = QtWidgets.QPushButton()
        self.blacklist_btn.setIcon(utils.get_icon("remove.svg"))
        self.blacklist_btn.setToolTip("Don't show this file again")
        self.blacklist_btn.setFixedSize(22, 22)
        self.blacklist_btn.clicked.connect(lambda: self.blacklistRequested.emit(self.path))
        self.btn_layout.addWidget(self.blacklist_btn)

        # 3. Whitelist Button
        self.whitelist_btn = QtWidgets.QPushButton()
        self.whitelist_btn.setIcon(utils.get_icon("whitelist.svg"))
        self.whitelist_btn.setToolTip("Remove from blacklist")
        self.whitelist_btn.setFixedSize(22, 22)
        self.whitelist_btn.clicked.connect(lambda: self.whitelistRequested.emit(self.path))
        self.btn_layout.addWidget(self.whitelist_btn)

        # 4. Remove Button (Trash) - Only for existing rigs
        self.remove_btn = QtWidgets.QPushButton()
        self.remove_btn.setIcon(utils.get_icon("trash.svg"))
        self.remove_btn.setToolTip("Delete from database (Keep file)")
        self.remove_btn.setFixedSize(22, 22)
        self.remove_btn.clicked.connect(lambda: self.removeRequested.emit(self.path))
        self.btn_layout.addWidget(self.remove_btn)

        # Initial visual update
        self.set_category(category)

    def resizeEvent(self, event):
        super(ManageRigsItemWidget, self).resizeEvent(event)
        self._update_path_display()

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        copy_act = menu.addAction("Copy path")

        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action == copy_act:
            QtWidgets.QApplication.clipboard().setText(self.path)

    def _update_path_display(self):
        """Update elided text on the path label with two-tone colors if needed."""
        width = self.path_lbl.width()
        if width <= 0:
            return

        metrics = QtGui.QFontMetrics(self.path_lbl.font())
        elided = metrics.elidedText(self.path, QtCore.Qt.ElideLeft, width)

        # Base colors
        dir_color = "gray"
        file_color = "#eee"

        # State-based color overrides
        if self._is_found:
            file_color = "#7cb380"  # Soft green
        else:
            file_color = "#aaa"

        # Split elided text into directory and filename
        idx = max(elided.rfind("/"), elided.rfind("\\"))
        if idx != -1:
            dir_part = elided[: idx + 1]
            file_part = elided[idx + 1 :]

            # Apply bold if added/found
            if self._is_found:
                file_part = "<b>{}</b>".format(file_part)

            rich_text = "<span style='color: {};'>{}</span><span style='color: {};'>{}</span>".format(
                dir_color, dir_part, file_color, file_part
            )
        else:
            rich_text = "<span style='color: {};'>{}</span>".format(file_color, elided)

        # Update if changed
        if self._last_rich_text != rich_text:
            self._last_rich_text = rich_text
            self.path_lbl.setText(rich_text)

    def paintEvent(self, event):
        # We handle text via rich text in resizeEvent/_update_path_display
        super(ManageRigsItemWidget, self).paintEvent(event)

    def set_added(self):
        """Update visual state when rig is added to DB."""
        self._is_found = True
        if self.category == "new":
            self.set_category("exists")
        else:
            self._last_rich_text = ""  # Force refresh
            self.update()

    def set_category(self, category):
        """Switch the category and update UI buttons/styles visibility."""
        self.category = category

        is_blacklisted = category == "blacklisted"

        # 1. Update Edit/Add Button
        self.edit_btn.setVisible(not is_blacklisted)
        if category == "new":
            self.edit_btn.setIcon(utils.get_icon("add.svg"))
            self.edit_btn.setToolTip("Add this rig")
        else:
            self.edit_btn.setIcon(utils.get_icon("edit.svg"))
            self.edit_btn.setToolTip("Edit the metadata of this rig")

        # 2. Update Blacklist/Whitelist/Trash Buttons
        self.blacklist_btn.setVisible(not is_blacklisted)
        self.whitelist_btn.setVisible(is_blacklisted)
        self.remove_btn.setVisible(category == "exists")

        # 3. Label Style (Using ID selector to protect tooltip inherited styles)
        if category == "exists" or self._is_found:
            self.path_lbl.setStyleSheet("QLabel#scanner_path_label { color: #aaa; }")
        else:
            self.path_lbl.setStyleSheet("QLabel#scanner_path_label { color: #eee; }")

        self._update_path_display()
        self.update()


class CollapsibleSection(QtWidgets.QWidget):
    """A section that can be toggled to show/hide its scrolled content."""

    def __init__(self, title, parent=None):
        super(CollapsibleSection, self).__init__(parent)
        self._items = []
        self._footers = []
        self._title = title

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.btn = QtWidgets.QPushButton(title, self)
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
        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setVisible(False)
        self.scroll.setStyleSheet("QScrollArea { border: 1px solid #333; border-top: none; }")

        self.container = QtWidgets.QWidget(self.scroll)
        self.content_layout = QtWidgets.QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(2)

        self.empty_lbl = QtWidgets.QLabel("No items", self.container)
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
        for w in self._footers:
            w.setVisible(checked)

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
            widget.hide()
            widget.setParent(None)

            if not self._items:
                self.empty_lbl.setVisible(True)

            self.update_title()

    def addFooterWidget(self, widget):
        """Add a widget that is below the scroll area but inside the collapsible part."""
        self._footers.append(widget)
        widget.setVisible(self.btn.isChecked())
        self.layout().addWidget(widget)

    def update_title(self):
        # Only count widgets that aren't separators
        rig_count = len([i for i in self._items if i.objectName() != "section_separator"])
        self.btn.setText("{} ({})".format(self._title, rig_count))


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
        self.setMouseTracking(True)
        self.resize(800, 600)

        self.initial_tab = initial_tab
        self.directory = directory
        self.rig_data = rig_data or {}
        self.blacklist = [utils.normpath_posix_keep_trailing(p) for p in blacklist] if blacklist else []
        self.collections = collections or []
        self.authors = authors or []
        self.tags = tags or []
        self.session_discovered_paths = set()

        # Settings
        self.settings = QtCore.QSettings(TOOL_TITLE, "RigManager")
        self._replacements_dirty = False

        self.existing_paths = {}  # Normalized lookup -- name
        self.alternative_paths = set()  # Normalized lookup set
        self._rebuild_existing_paths()
        self._update_metadata()

        self._widgets_map = {}  # original path -- widget

        self._build_ui()
        self._populate_existing()
        if self.directory:
            self._start_scan()

    def resizeEvent(self, event):
        super(ManageRigsDialog, self).resizeEvent(event)
        # Re-calc elision on resize if we have a path showing
        if hasattr(self, "lbl_scan_path") and self.lbl_scan_path.isVisible():
            path = self._get_status_path()
            self.lbl_scan_path.setText("<i>{}</i>".format(path))
            self.lbl_scan_path.setToolTip(self.directory)

    def closeEvent(self, event):
        """Ensure the background worker is stopped when closing."""
        self._stop_scan()
        super(ManageRigsDialog, self).closeEvent(event)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "api_key_input", None) and event.type() == QtCore.QEvent.FocusOut:
            if self.api_key_input.echoMode() == QtWidgets.QLineEdit.Normal:
                self._toggle_api_key_visibility()
        return super(ManageRigsDialog, self).eventFilter(obj, event)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self.tabs)

        # --- Tab 1: Rigs ---
        self.tab_rigs = QtWidgets.QWidget(self.tabs)
        rigs_layout = QtWidgets.QVBoxLayout(self.tab_rigs)

        self.scan_info_layout = QtWidgets.QHBoxLayout()
        self.lbl_scan_prefix = QtWidgets.QLabel("", self.tab_rigs)
        self.lbl_scan_prefix.setFixedWidth(60)
        self.lbl_scan_prefix.setFixedHeight(24)

        self.lbl_scan_path = ContextLabel("", is_path=True, parent=self.tab_rigs)
        self.lbl_scan_path.setFixedHeight(24)
        # Use Minimum so it takes its size hint but can shrink for elision
        self.lbl_scan_path.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)

        self.lbl_loading_dots = LoadingDotsWidget(self.tab_rigs)
        self.lbl_loading_dots.setFixedHeight(24)
        self.lbl_loading_dots.setFixedWidth(25) # Fixed width for dot area
        self.lbl_loading_dots._timer.timeout.connect(self._update_discovery_section_dots)

        visible = bool(self.directory)
        self.lbl_scan_prefix.setVisible(visible)
        self.lbl_scan_path.setVisible(visible)
        self.lbl_loading_dots.setVisible(visible)
        if visible:
            self.lbl_scan_prefix.setText("Scanning:")
            # Use a conservative initial width or it will be elided to nothing before first show
            self.lbl_scan_path.setText("<i>{}</i>".format(self.directory))

        self.btn_stop_scan = QtWidgets.QPushButton("Stop", self.tab_rigs)
        self.btn_stop_scan.setFixedWidth(60)
        self.btn_stop_scan.setFixedHeight(24)
        self.btn_stop_scan.setVisible(visible)
        self.btn_stop_scan.clicked.connect(self._stop_scan)

        self.scan_info_layout.setSpacing(0)
        self.scan_info_layout.addWidget(self.lbl_scan_prefix)
        self.scan_info_layout.addSpacing(6)  # Space after prefix
        self.scan_info_layout.addWidget(self.lbl_scan_path)
        self.scan_info_layout.addWidget(self.lbl_loading_dots)
        self.scan_info_layout.addStretch(1)  # Stretch factor after the dots
        self.scan_info_layout.addSpacing(6)  # Space before stop button
        self.scan_info_layout.addWidget(self.btn_stop_scan)

        rigs_layout.addLayout(self.scan_info_layout)

        # New Rigs Section
        self.sec_new = CollapsibleSection("Discovered New Rigs", parent=self.tab_rigs)
        self.sec_new.setVisible(bool(self.directory))
        rigs_layout.addWidget(self.sec_new)
        self.sec_new.btn.setChecked(True)  # Expand by default

        # AI Button (Inside sec_new as footer)
        self.ai_btn = QtWidgets.QPushButton(self.tab_rigs)
        self.ai_btn.setText("Auto-Tag with AI")
        self.ai_btn.setVisible(False)
        self.ai_btn.setEnabled(False)
        self.ai_btn.setToolTip("Once new rigs are discovered, click to auto-tag them using AI.")
        self.ai_btn.clicked.connect(self._run_ai_auto_tag)
        self.sec_new.addFooterWidget(self.ai_btn)

        # Initialize button style (must call after settings are accessible)
        QtCore.QTimer.singleShot(0, self._update_ai_button_style)

        # Existing Rigs Section
        self.sec_exists = CollapsibleSection("In Database", parent=self.tab_rigs)
        self.sec_exists.set_empty_text(
            "No rigs in database." if not self.directory else "No existing rigs found in this folder."
        )
        # If managing (no dir), expand by default
        rigs_layout.addWidget(self.sec_exists)
        if not self.directory:
            self.sec_exists.btn.setChecked(True)

        # Blacklisted Section
        self.sec_black = CollapsibleSection("Blacklisted", parent=self.tab_rigs)
        self.sec_black.set_empty_text("No blacklisted files.")
        rigs_layout.addWidget(self.sec_black)

        rigs_layout.addStretch()

        self.tabs.addTab(self.tab_rigs, "Rigs")

        # --- Tab 2: Settings ---
        self.tab_settings = QtWidgets.QWidget(self.tabs)
        self._build_settings_tab()
        self.tabs.addTab(self.tab_settings, "Settings")

        # Set initial tab
        self.tabs.setCurrentIndex(self.initial_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._last_tab_index = self.initial_tab

        # --- Main Footer ---
        footer = QtWidgets.QHBoxLayout()
        # footer.setContentsMargins(10, 0, 10, 10) # Optional spacing

        btn_scan = QtWidgets.QPushButton("Scan Folder", self)
        btn_scan.setIcon(utils.get_icon("search.svg"))
        btn_scan.clicked.connect(self._trigger_scan_folder)

        btn_add = QtWidgets.QPushButton("Add Manually", self)
        btn_add.setIcon(utils.get_icon("add.svg"))
        btn_add.clicked.connect(self._trigger_add_manual)

        self.done_btn = QtWidgets.QPushButton("Done", self)
        self.done_btn.clicked.connect(self.accept)

        footer.addWidget(btn_scan)
        footer.addWidget(btn_add)
        footer.addStretch()
        footer.addWidget(self.done_btn)

        layout.addLayout(footer)

    def _build_settings_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_settings)

        # 0. Blocked Paths
        grp_blocked = QtWidgets.QGroupBox("Scanning Settings")
        lay_blocked = QtWidgets.QVBoxLayout(grp_blocked)

        lbl_blocked = QtWidgets.QLabel("Blocked Folder Patterns:")
        lbl_blocked.setStyleSheet("color: #aaa; margin-bottom: 2px;")
        lay_blocked.addWidget(lbl_blocked)

        self.blocked_paths_editor = TagEditorWidget(parent=self)
        self.blocked_paths_editor.setPlaceholderText("Add pattern (e.g. .git, temp)...")
        # Connect to save on change
        self.blocked_paths_editor.tagsChanged.connect(self._save_blocked_paths_from_ui)
        lay_blocked.addWidget(self.blocked_paths_editor)

        blocked_desc = QtWidgets.QLabel(
            "Exclude directories during scans using glob patterns. Use '.*' for prefixes, "
            "'*.anim' for suffixes, or exact directory names to block them entirely."
        )
        blocked_desc.setWordWrap(True)
        blocked_desc.setStyleSheet("color: #969696; margin-bottom: 5px;")
        lay_blocked.addWidget(blocked_desc)

        layout.addWidget(grp_blocked, 0)

        # 1. Path Replacements
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
        add_btn.clicked.connect(lambda: self._add_replacement_row())
        lay_add.addWidget(add_btn)
        lay_add.addStretch()
        lay_paths.addLayout(lay_add)

        layout.addWidget(grp_paths, 0)  # No stretch, size by content

        # 2. AI Integration
        self.grp_ai = QtWidgets.QGroupBox("AI Integration")
        self.grp_ai.setCheckable(True)
        self.grp_ai.setChecked(self.settings.value("ai_enabled", "true") == "true")
        self.grp_ai.toggled.connect(self._on_ai_toggled)
        lay_ai = QtWidgets.QVBoxLayout(self.grp_ai)

        # Explanatory Text
        ai_desc = QtWidgets.QLabel(
            "Use AI to automatically detect character names, tags, and collections from files "
            "during a folder scan.\nThis creates database entries for new rigs in one click."
        )
        ai_desc.setWordWrap(True)
        ai_desc.setStyleSheet("color: #969696; margin-bottom: 5px;")
        lay_ai.addWidget(ai_desc)

        # Endpoint Selection
        lay_endpoint = QtWidgets.QHBoxLayout()
        lay_endpoint.addWidget(QtWidgets.QLabel("AI Endpoint:"))
        self.ai_endpoint_combo = QtWidgets.QComboBox()

        endpoints = ["Gemini", "ChatGPT", "Claude", "Grok", "OpenRouter", "Custom"]
        for ep in endpoints:
            self.ai_endpoint_combo.addItem(utils.get_icon("ai/{}.svg".format(ep.lower())), ep)

        saved_endpoint = self.settings.value("ai_endpoint", "Gemini")
        # Find index for saved endpoint
        idx = self.ai_endpoint_combo.findText(saved_endpoint)
        if idx != -1:
            self.ai_endpoint_combo.setCurrentIndex(idx)

        self.ai_endpoint_combo.currentTextChanged.connect(self._on_ai_endpoint_changed)
        lay_endpoint.addWidget(self.ai_endpoint_combo)
        lay_ai.addLayout(lay_endpoint)

        # Custom URL (visible if Custom is selected)
        self.custom_url_input = QtWidgets.QLineEdit()
        self.custom_url_input.setPlaceholderText("Custom API Endpoint")
        self.custom_url_input.setText(self.settings.value("ai_custom_url", ""))
        self.custom_url_input.textChanged.connect(lambda txt: self.settings.setValue("ai_custom_url", txt))
        self.custom_url_input.setVisible(saved_endpoint == "Custom")
        lay_ai.addWidget(self.custom_url_input)

        # Model Selection
        lay_model = QtWidgets.QHBoxLayout()
        lay_model.addWidget(QtWidgets.QLabel("Model:"))
        self.model_combo = ModelComboBox()
        self.model_combo.setFixedHeight(25)
        self.model_combo.setEditable(True)
        self.model_combo.firstShowPopup.connect(lambda: self._refresh_ai_models(silent=True))
        # Pre-fill some defaults if empty
        saved_model = self.settings.value("ai_model_{}".format(saved_endpoint), "")
        if not saved_model:
            defaults = {
                "Gemini": "gemini-2.5-flash",
                "ChatGPT": "gpt-4o",
                "Claude": "claude-3-5-sonnet-20241022",
                "Grok": "grok-2",
                "OpenRouter": "google/gemini-2.0-flash-exp:free",
            }
            saved_model = defaults.get(saved_endpoint, "")
        if saved_model:
            self.model_combo.addItem(saved_model)

        self.model_combo.currentTextChanged.connect(
            lambda txt: self.settings.setValue(
                "ai_model_{}".format(self.ai_endpoint_combo.currentText()), txt
            )
        )
        lay_model.addWidget(self.model_combo, 1)

        btn_refresh_models = QtWidgets.QPushButton("Refresh")
        btn_refresh_models.setFixedHeight(25)
        btn_refresh_models.setFixedWidth(60)
        btn_refresh_models.clicked.connect(self._refresh_ai_models)
        lay_model.addWidget(btn_refresh_models)
        lay_ai.addLayout(lay_model)

        # API Key
        lay_key = QtWidgets.QHBoxLayout()
        lay_key.addWidget(QtWidgets.QLabel("API Key:"))
        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setFixedHeight(25)
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        # Visibility toggle
        self.show_key_action = self.api_key_input.addAction(
            utils.get_icon("eye_off.svg"), QtWidgets.QLineEdit.TrailingPosition
        )
        self.show_key_action.setToolTip("Show/Hide API Key")
        self.show_key_action.triggered.connect(self._toggle_api_key_visibility)
        self.api_key_input.installEventFilter(self)

        # Load key for current endpoint
        cur_key = self.settings.value("ai_api_key_{}".format(saved_endpoint), "")
        self.api_key_input.setText(cur_key)
        self.api_key_input.textChanged.connect(self._save_ai_api_key)
        lay_key.addWidget(self.api_key_input)
        lay_ai.addLayout(lay_key)

        self.lbl_ai_info = QtWidgets.QLabel()
        self.lbl_ai_info.setOpenExternalLinks(True)
        self.lbl_ai_info.setStyleSheet("font-size: 7.5pt;")
        lay_ai.addWidget(self.lbl_ai_info)

        self._update_ai_info_label(saved_endpoint)

        layout.addWidget(self.grp_ai, 0)

        # Add a stretch at the bottom to absorb empty space
        layout.addStretch(1)

        # Load and populate initial states
        self._load_blocked_paths_ui()
        self._load_replacements_ui()
        # Ensure ai_btn reflects initial state
        QtCore.QTimer.singleShot(0, lambda: self._on_ai_toggled(self.grp_ai.isChecked()))

    def _get_blocked_paths(self):
        """Helper to get current blocked paths from settings."""
        raw = self.settings.value("blocked_paths", '[".*", "*.anim"]')
        try:
            data = json.loads(raw)
            # Migration check: if someone has the old "." or ".anim", convert them to glob style
            migrated = []
            for t in (data if isinstance(data, list) else [".*", "*.anim"]):
                clean = str(t).strip()
                if clean == ".":
                    clean = ".*"
                elif clean == ".anim":
                    clean = "*.anim"
                migrated.append(clean)
            return migrated
        except Exception:
            return [".*", "*.anim"]

    def _get_replacements(self):
        """Helper to get current replacements from settings."""
        raw = self.settings.value("path_replacements", "[]")
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _load_blocked_paths_ui(self):
        paths = self._get_blocked_paths()
        self.blocked_paths_editor.setTags(paths)

    def _save_blocked_paths_from_ui(self):
        tags = self.blocked_paths_editor.getTags()
        self.settings.setValue("blocked_paths", json.dumps(tags))

    def _rebuild_existing_paths(self):
        """Rebuilds the existing_paths lookup, applying current path replacements."""
        self.existing_paths = {}
        self.alternative_paths = set()
        replacements = self._get_replacements()

        for name, d in self.rig_data.items():
            if name.startswith("_"):
                continue

            # Map main path
            main_p = d.get("path")
            if main_p:
                # Apply replacements before normalization/lookup
                run_p = utils.apply_path_replacements(main_p, replacements)
                norm_p = utils.normpath_posix_keep_trailing(run_p)
                lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()
                self.existing_paths[lookup_p] = name

            # Map alternatives
            for alt in d.get("alternatives", []):
                if not alt:
                    continue
                run_p = utils.apply_path_replacements(alt, replacements)
                norm_p = utils.normpath_posix_keep_trailing(run_p)
                lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()
                self.existing_paths[lookup_p] = name
                self.alternative_paths.add(lookup_p)

    def _load_replacements_ui(self):
        self.replacements_list.clear()
        data = self._get_replacements()

        if data:
            for find_txt, rep_txt in data:
                self._add_replacement_row(find_txt, rep_txt)
        else:
            self._add_replacement_row()

    def _add_replacement_row(self, find_val="", rep_val=""):
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(QtCore.QSize(0, 42))  # Fixed height for row

        row_widget = QtWidgets.QWidget(self.replacements_list)
        row_lay = QtWidgets.QHBoxLayout(row_widget)
        row_lay.setContentsMargins(5, 5, 5, 5)
        row_lay.setSpacing(8)

        # Handle
        handle_lbl = QtWidgets.QLabel("☰", row_widget)  # Unicode trigram for handle
        handle_lbl.setStyleSheet("QLabel { color: #868686; font-size: 15px; }")
        handle_lbl.setCursor(QtCore.Qt.OpenHandCursor)
        handle_lbl.setMouseTracking(True)
        handle_lbl.setFixedWidth(20)
        handle_lbl.setAlignment(QtCore.Qt.AlignCenter)
        handle_lbl.setToolTip("Drag to reorder")
        row_lay.addWidget(handle_lbl)

        find_edit = QtWidgets.QLineEdit(find_val)
        find_edit.setPlaceholderText("e.g. Z:/Server/Rigs")
        find_edit.editingFinished.connect(self._save_path_replacements_from_ui)
        row_lay.addWidget(find_edit)

        arrow_lbl = QtWidgets.QLabel(row_widget)
        arrow_lbl.setPixmap(utils.get_icon("right_arrow.svg").pixmap(16, 16))
        row_lay.addWidget(arrow_lbl)

        rep_edit = QtWidgets.QLineEdit(rep_val)
        rep_edit.setPlaceholderText("e.g. Z:/Rigs")
        rep_edit.editingFinished.connect(self._save_path_replacements_from_ui)
        row_lay.addWidget(rep_edit)

        def _update_row_tooltip():
            f = find_edit.text()
            r = rep_edit.text()
            row_widget.setToolTip("{} -> {}".format(f, r) if (f or r) else "")

        # Update on text change
        find_edit.textChanged.connect(_update_row_tooltip)
        rep_edit.textChanged.connect(_update_row_tooltip)
        # Auto-save changes
        find_edit.textChanged.connect(self._save_path_replacements_from_ui)
        rep_edit.textChanged.connect(self._save_path_replacements_from_ui)

        _update_row_tooltip()

        del_btn = QtWidgets.QPushButton(row_widget)
        del_btn.setIcon(utils.get_icon("trash.svg"))
        del_btn.setFixedSize(20, 20)
        del_btn.setFlat(True)
        del_btn.setCursor(QtCore.Qt.PointingHandCursor)
        del_btn.setToolTip("Remove this replacement")
        del_btn.clicked.connect(lambda: self._remove_replacement_row(item))

        row_lay.addWidget(del_btn)

        self.replacements_list.addItem(item)
        self.replacements_list.setItemWidget(item, row_widget)
        self.replacements_list.updateGeometry()

        # Ensure save is called if this is a new empty row adding
        if not find_val and not rep_val:
            self._save_path_replacements_from_ui()

    def _remove_replacement_row(self, item):
        row = self.replacements_list.row(item)
        self.replacements_list.takeItem(row)
        self.replacements_list.updateGeometry()
        # Schedule save
        QtCore.QTimer.singleShot(10, self._save_path_replacements_from_ui)

    def _on_tab_changed(self, index):
        """Trigger updates when switching between tabs."""
        # If moving from Settings to Rigs, refresh the rigs view if changed
        if index == 0 and self._last_tab_index == 1 and self._replacements_dirty:
            self._refresh_rigs_tab()

        self._last_tab_index = index

    def _refresh_rigs_tab(self):
        """
        Re-evaluates all paths and statuses in the UI based on current settings.
        Maintains the current scan context while updating display and categorized lists.
        """
        self._replacements_dirty = False

        # Capture scroll positions
        scroll_exists = self.sec_exists.scroll.verticalScrollBar().value()
        scroll_black = self.sec_black.scroll.verticalScrollBar().value()
        scroll_new = self.sec_new.scroll.verticalScrollBar().value()

        self._rebuild_existing_paths()

        # Clear existing and blacklist layouts (but keep new)
        while self.sec_exists._items:
            self.sec_exists.removeWidget(self.sec_exists._items[0])
        while self.sec_black._items:
            self.sec_black.removeWidget(self.sec_black._items[0])

        # Re-populate them
        self._populate_existing()

        # 2. Update New Rigs section
        # We need to re-verify if they are still 'new' or now belong to existing/blacklist
        replacements = self._get_replacements()

        # Convert blacklist and existing sets for quick lookup
        lookup_existing = set(self.existing_paths.keys())
        lookup_blacklist = set()
        for p in self.blacklist:
            run_p = utils.apply_path_replacements(p, replacements)
            norm_p = utils.normpath_posix_keep_trailing(run_p)
            lookup_blacklist.add(norm_p if sys.platform != "win32" else norm_p.lower())

        stale_widgets = []
        for widget in self.sec_new._items:
            path = widget.path  # This is the disk path found by scanner
            norm_p = utils.normpath_posix_keep_trailing(path)
            lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()

            # Check if it should move
            target_cat = "new"
            if lookup_p in lookup_blacklist:
                target_cat = "blacklisted"
            elif lookup_p in lookup_existing:
                target_cat = "exists"

            if target_cat != "new":
                stale_widgets.append((widget, target_cat))
            else:
                widget.update()

        # Move items that are no longer 'new'
        for widget, cat in stale_widgets:
            self.sec_new.removeWidget(widget)

        # 3. Add back any discovered items that are now 'new' (e.g. after whitelisting)
        current_new_paths = [w.path for w in self.sec_new._items]
        for path in self.session_discovered_paths:
            # We must normalize the disk path using the same logic as the scanner/refresh
            norm_p = utils.normpath_posix_keep_trailing(path)
            lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()

            if lookup_p not in lookup_blacklist and lookup_p not in lookup_existing:
                if path not in current_new_paths:
                    self._on_file_discovered(path, "new")

        self.update()

        # Restore scroll positions with a small delay to allow layouts to calculate
        def restore():
            self.sec_exists.scroll.verticalScrollBar().setValue(scroll_exists)
            self.sec_black.scroll.verticalScrollBar().setValue(scroll_black)
            self.sec_new.scroll.verticalScrollBar().setValue(scroll_new)

        QtCore.QTimer.singleShot(10, restore)

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
                        f_txt = find_edit.text()
                        r_txt = rep_edit.text()
                        # Only save if at least find_txt has something
                        if f_txt or r_txt:
                            item = [
                                utils.normpath_posix_keep_trailing(f_txt),
                                utils.normpath_posix_keep_trailing(r_txt),
                            ]
                            if item not in data:
                                data.append(item)

        json_str = json.dumps(data)
        self.settings.setValue("path_replacements", json_str)
        self._replacements_dirty = True

    @staticmethod
    def get_unique_name(name, existing_list):
        if name not in existing_list:
            return name
        base = name
        counter = 2
        while True:
            new_name = "{} {}".format(base, counter)
            if new_name not in existing_list:
                return new_name
            counter += 1

    def _populate_existing(self):
        # Populate sec_exists and sec_black from full database since no directory scan
        self.sec_exists.set_empty_text("Database is empty.")
        replacements = self._get_replacements()

        # Build normalized blacklist set for quick skipping in the database view
        norm_blacklist = set()
        for p in self.blacklist:
            run_p = utils.apply_path_replacements(p, replacements)
            norm_p = utils.normpath_posix_keep_trailing(run_p)
            norm_blacklist.add(norm_p if sys.platform != "win32" else norm_p.lower())

        all_db_items = []
        # Gather and verify existence for sorting
        for name, data in self.rig_data.items():
            if name.startswith("_"):
                continue

            # Main Path
            main_p = data.get("path", "")
            if main_p:
                run_p = utils.apply_path_replacements(main_p, replacements)
                # Skip if blacklisted
                lookup_p = utils.normpath_posix_keep_trailing(run_p)
                if (lookup_p if sys.platform != "win32" else lookup_p.lower()) in norm_blacklist:
                    continue

                all_db_items.append(
                    {
                        "display": run_p,
                        "original": main_p,
                        "is_alt": False,
                        "rig_name": name,
                        "exists": os.path.exists(run_p),
                    }
                )

            # Alternatives
            for alt in data.get("alternatives", []):
                if not alt:
                    continue
                run_p = utils.apply_path_replacements(alt, replacements)
                # Skip if blacklisted
                lookup_p = utils.normpath_posix_keep_trailing(run_p)
                if (lookup_p if sys.platform != "win32" else lookup_p.lower()) in norm_blacklist:
                    continue

                all_db_items.append(
                    {
                        "display": run_p,
                        "original": alt,
                        "is_alt": True,
                        "rig_name": name,
                        "exists": os.path.exists(run_p),
                    }
                )

        # 1. Populate In Database
        self._populate_section_view(self.sec_exists, all_db_items)

        # 2. Populate Blacklist
        blacklist_items = []
        for p in self.blacklist:
            run_p = utils.apply_path_replacements(p, replacements)
            blacklist_items.append(
                {"display": run_p, "original": p, "exists": os.path.exists(run_p), "category": "blacklisted"}
            )

        self._populate_section_view(self.sec_black, blacklist_items)

    def _populate_section_view(self, section, items):
        """Helper to fill a CollapsibleSection with availability-sorted items."""
        # Sort: Found first, then alpha display name
        items.sort(key=lambda x: (not x["exists"], x["display"].lower()))

        has_found = any(e["exists"] for e in items)
        separator_added = False

        for entry in items:
            run_p = entry["display"]
            exists_on_disk = entry["exists"]
            category = entry.get("category", "exists")

            # Insert separator if mixed status
            if not exists_on_disk and has_found and not separator_added:
                sep = ManageRigsSeparatorWidget("NOT FOUND")
                section.addWidget(sep)
                separator_added = True

            item = ManageRigsItemWidget(run_p, category, is_found=exists_on_disk, parent=section)

            # Connect all signals regardless of initial category to allow fluid UI state changes
            item.editRequested.connect(self._on_edit_request)
            item.blacklistRequested.connect(self._on_blacklist_request)
            item.whitelistRequested.connect(self._on_whitelist_request)
            item.removeRequested.connect(self._on_remove_request)

            if category == "exists" and entry.get("is_alt"):
                item.edit_btn.setToolTip(
                    "This path is an alternative for rig: '{}'".format(entry.get("rig_name"))
                )

            section.addWidget(item)
            # Link by display path for runtime interaction
            self._widgets_map[run_p] = item

    def _clear_lists(self):
        """Clears all items from the NEW list only."""
        while self.sec_new._items:
            self.sec_new.removeWidget(self.sec_new._items[0])

        # We also need to remove 'new' items from _widgets_map to avoid stale references
        # but keep 'exists' and 'blacklisted' ones.
        stale_paths = [p for p, item in self._widgets_map.items() if item.category == "new"]
        for p in stale_paths:
            del self._widgets_map[p]

    def _trigger_scan_folder(self):
        self.tabs.setCurrentIndex(0)
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory to Scan")
        if not directory:
            return

        self.directory = os.path.normpath(directory)
        self.lbl_scan_prefix.setText("Scanning:")
        self.lbl_scan_prefix.setVisible(True)
        # Use elided path
        self.lbl_scan_path.setText("<i>{}</i>".format(self._get_status_path()))
        self.lbl_scan_path.setVisible(True)

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

        self.ai_btn.setEnabled(False)
        self.ai_btn.setToolTip("Once new rigs are discovered, click to auto-tag them using AI.")
        self._start_scan()

    def _trigger_add_manual(self):
        self.tabs.setCurrentIndex(0)
        file_filter = "Maya Files (*.ma *.mb);;Maya ASCII (*.ma);;Maya Binary (*.mb)"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Rig File", "", file_filter)
        if not path:
            return

        path = os.path.normpath(path)

        # Check duplicates using replaced (runtime) paths
        lookup = path if sys.platform != "win32" else path.lower()
        if lookup in self.existing_paths:
            name = self.existing_paths[lookup]
            # Find matching widget for this path
            existing_item = self._widgets_map.get(lookup)

            QtWidgets.QMessageBox.warning(
                self,
                "Duplicate Found",
                "The rig '{}' ({}) is already in the database.".format(name, os.path.basename(path)),
            )

            if existing_item:
                # Highlight existing
                self.sec_exists.btn.setChecked(True)
                self.sec_exists.scroll.ensureWidgetVisible(existing_item)

                orig_style = existing_item.styleSheet()
                # Flashing style - Target ONLY the frame using ID selector to avoid inner widget bleed
                existing_item.setStyleSheet(
                    "#ManageRigsItemWidget { background-color: #554444; border: 1px solid #DD5555; }"
                )
                QtCore.QTimer.singleShot(2000, lambda: existing_item.setStyleSheet(orig_style))

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
                if res.get("is_alternative"):
                    target_name = res["name"]
                    target_data = self.rig_data.get(target_name)
                    if target_data:
                        alts = target_data.get("alternatives", [])
                        new_path = res["data"]["path"]
                        if new_path not in alts:
                            alts.append(new_path)
                            target_data["alternatives"] = alts
                            # Signal to main to update the target rig
                            self.rigAdded.emit(target_name, target_data)
                else:
                    self.rigAdded.emit(res["name"], res["data"])
                    self.rig_data[res["name"]] = res["data"]
                    # Update local lookup for duplicate checking in the same sesssion
                    self.existing_paths[lookup] = res["name"]

                # Add to existing list directly
                item = ManageRigsItemWidget(path, "exists", is_found=True)
                item.set_added()
                item.editRequested.connect(self._on_edit_request)
                item.blacklistRequested.connect(self._on_blacklist_request)
                self.sec_exists.addWidget(item)
                self._widgets_map[path] = item
                # Refresh UI to ensure sorting/separators etc are right (manual add might change things)
                self._refresh_rigs_tab()

    def _on_ai_toggled(self, enabled):
        """Enable/disable AI functionality and UI."""
        self.settings.setValue("ai_enabled", "true" if enabled else "false")

        # Refresh info label to update link color if needed
        endpoint = self.ai_endpoint_combo.currentText()
        self._update_ai_info_label(endpoint)
        if hasattr(self, "ai_btn"):
            # Disable the ai_btn in the rigs tab
            self.ai_btn.setVisible(enabled)

    def _on_ai_endpoint_changed(self, endpoint):
        self.settings.setValue("ai_endpoint", endpoint)
        self.custom_url_input.setVisible(endpoint == "Custom")
        self.model_combo.reset_fetch_state()

        # Update AI Button style immediately
        self._update_ai_button_style(endpoint)
        # Swap API Key
        key = self.settings.value("ai_api_key_{}".format(endpoint), "")
        self.api_key_input.setText(key)

        # Swap Model
        model = self.settings.value("ai_model_{}".format(endpoint), "")
        if not model:
            defaults = {
                "Gemini": "gemini-2.5-flash",
                "ChatGPT": "gpt-4o",
                "Claude": "claude-3-5-sonnet-20241022",
                "Grok": "grok-2",
                "OpenRouter": "google/gemini-2.0-flash-exp:free",
            }
            model = defaults.get(endpoint, "")

        self.model_combo.clear()
        if model:
            self.model_combo.addItem(model)
        self.model_combo.setCurrentText(model)

        self._update_ai_info_label(endpoint)

    def _toggle_api_key_visibility(self):
        if self.api_key_input.echoMode() == QtWidgets.QLineEdit.Password:
            self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.show_key_action.setIcon(utils.get_icon("eye.svg"))
        else:
            self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self.show_key_action.setIcon(utils.get_icon("eye_off.svg"))

    def _save_ai_api_key(self, txt):
        endpoint = self.ai_endpoint_combo.currentText()
        self.settings.setValue("ai_api_key_{}".format(endpoint), txt)

    def _update_ai_info_label(self, endpoint):
        provider_info = {
            "Gemini": {"url": "https://aistudio.google.com/api-keys", "name": "Google AI Studio"},
            "ChatGPT": {"url": "https://platform.openai.com/api-keys", "name": "OpenAI Dashboard"},
            "Claude": {"url": "https://console.anthropic.com/settings/keys", "name": "Anthropic Console"},
            "Grok": {"url": "https://x.ai/api", "name": "X.ai Console"},
            "OpenRouter": {"url": "https://openrouter.ai/keys", "name": "OpenRouter Dashboard"},
            "Custom": {"url": "", "name": ""},
        }

        info = provider_info.get(endpoint, {"url": "", "name": ""})
        url = info["url"]
        name = info["name"]

        enabled = self.grp_ai.isChecked()

        if url:
            if enabled:
                self.lbl_ai_info.setText("Get your API key from: <a href='{}'>{}</a>".format(url, name))
            else:
                # Make the link look darker/disabled when the groupbox is unchecked
                self.lbl_ai_info.setText(
                    "Get your API key from: <a href='{}' style='color: #5b738a;'>{}</a>".format(url, name)
                )
            self.lbl_ai_info.setVisible(True)
        else:
            self.lbl_ai_info.setVisible(False)

    def _refresh_ai_models(self, silent=False):
        endpoint = self.ai_endpoint_combo.currentText()
        api_key = self.api_key_input.text()
        custom_url = self.custom_url_input.text()

        if not api_key:
            if not silent:
                QtWidgets.QMessageBox.warning(self, "No API Key", "Please provide an API key first.")
            return

        # Capture the current value in the UI to preserve it if it still exists after refresh
        current_ui_model = self.model_combo.currentText()
        if current_ui_model in ["Fetching models...", "No models found"]:
            current_ui_model = ""

        # Simple indicator
        self.model_combo.clear()
        self.model_combo.addItem("Fetching models...")

        # Select config without if/elif blocks
        config = {
            "Gemini": {
                "url": "https://generativelanguage.googleapis.com/v1beta/models?key={}".format(api_key),
                "headers": {},
            },
            "ChatGPT": {
                "url": "https://api.openai.com/v1/models",
                "headers": {"Authorization": "Bearer {}".format(api_key)},
            },
            "Grok": {
                "url": "https://api.x.ai/v1/models",
                "headers": {"Authorization": "Bearer {}".format(api_key)},
            },
            "Claude": {
                "url": "https://api.anthropic.com/v1/models",
                "headers": {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            },
            "OpenRouter": {
                "url": "https://openrouter.ai/api/v1/models",
                "headers": {"Authorization": "Bearer {}".format(api_key)},
            },
            "Custom": {
                "url": custom_url.replace("/chat/completions", "/models") if custom_url else "",
                "headers": {"Authorization": "Bearer {}".format(api_key)},
            },
        }

        cfg = config.get(endpoint, {})
        url = cfg.get("url", "")
        headers = cfg.get("headers", {})

        def _on_fetched(models):
            self.model_combo.clear()
            if models:
                self.model_combo.addItems(models)
                # Priority: 1. Model that was just in the UI, 2. Model from settings
                target = current_ui_model or self.settings.value("ai_model_{}".format(endpoint), "")
                idx = self.model_combo.findText(target)
                if idx != -1:
                    self.model_combo.setCurrentIndex(idx)
                elif models:
                    # If target not found, select first item instead of leaving blank
                    self.model_combo.setCurrentIndex(0)

                # Finally signal the combo that it can open now if it was waiting
                self.model_combo.mark_fetched()
            else:
                self.model_combo.addItem("No models found")
                self.model_combo.mark_fetched()
                if not silent:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Fetch Error",
                        "Failed to fetch models for {}. Check your API key and connection.".format(endpoint),
                    )

        # We can use a small thread for this to not block UI
        class FetchWorker(QtCore.QThread):
            done = QtCore.Signal(list)

            def run(self):
                # Pass url and headers directly as requested
                models = utils.get_ai_models(url, headers)
                self.done.emit(models or [])

        self._fetch_worker = FetchWorker(self)
        self._fetch_worker.done.connect(_on_fetched)
        self._fetch_worker.start()

    def _update_ai_button_style(self, endpoint=None):
        """Updates the AI button text and icon based on the current endpoint."""
        if not endpoint:
            endpoint = self.settings.value("ai_endpoint", "Gemini")
        self.ai_btn.setText("Auto-Tag with {} AI".format(endpoint))
        self.ai_btn.setIcon(utils.get_icon("ai/{}.svg".format(endpoint.lower())))

    def _run_ai_auto_tag(self):
        enabled = self.settings.value("ai_enabled", "true") == "true"
        if not enabled:
            return

        endpoint = self.ai_endpoint_combo.currentText()
        api_key = self.settings.value("ai_api_key_{}".format(endpoint), "")
        model = self.settings.value("ai_model_{}".format(endpoint), "")
        custom_url = self.settings.value("ai_custom_url", "")

        if not api_key:
            QtWidgets.QMessageBox.warning(
                self, "No API Key", "Please set {} API Key in Settings tab.".format(endpoint)
            )
            return

        # Gather new paths
        new_paths = []
        for widget in self.sec_new._items:
            if isinstance(widget, ManageRigsItemWidget):
                new_paths.append(widget.path)

        if not new_paths:
            return

        self.sec_new.setEnabled(False)
        self.ai_btn.setEnabled(False)
        self.ai_btn.setToolTip("Once new rigs are discovered, click to auto-tag them using AI.")
        self.ai_btn.setText("Processing with {}...".format(endpoint))

        self.ai_worker = AIWorker(endpoint, model, api_key, new_paths, custom_url, self)
        self.ai_worker.finished.connect(self._on_ai_finished)
        self.ai_worker.error.connect(self._on_ai_error)
        self.ai_worker.start()

    def _on_ai_error(self, error):
        if hasattr(self, "sec_new"):
            self.sec_new.setEnabled(True)
            if self.sec_new._items:
                self.ai_btn.setEnabled(True)
                self.ai_btn.setToolTip("Auto-tag new rigs with metadata using AI.")
        self._update_ai_button_style()

        endpoint = self.ai_endpoint_combo.currentText()

        QtWidgets.QMessageBox.warning(self, "{} AI".format(endpoint), error)

    def _on_ai_finished(self, results):
        if hasattr(self, "sec_new"):
            self.sec_new.setEnabled(True)
            if self.sec_new._items:
                self.ai_btn.setEnabled(True)
                self.ai_btn.setToolTip("Auto-tag new rigs with metadata using AI.")
        self._update_ai_button_style()

        endpoint = self.ai_endpoint_combo.currentText()

        if not results:
            QtWidgets.QMessageBox.warning(self, "{} AI".format(endpoint), "Empty result.")
            return

        # Results is dict: { "CharacterName": { "path": ..., "tags": ... } }
        # The result keys are character names.

        count = 0
        for char_name, data in results.items():
            path = data.get("path")
            if not path:
                continue

            norm_p = utils.normpath_posix_keep_trailing(path)
            matching_widget = None
            for p, wid in self._widgets_map.items():
                if utils.normpath_posix_keep_trailing(p) == norm_p:
                    matching_widget = wid
                    break

            if matching_widget:
                # Ensure unique name across database
                final_name = self.get_unique_name(char_name, list(self.rig_data.keys()))

                # Automate "Add"
                # We Simulate the result data structure expected by rigAdded
                res_data = {
                    "path": path,
                    "image": "",  # AI returns null
                    "tags": data.get("tags", []),
                    "collection": data.get("collection") or "Empty",
                    "author": data.get("author") or "Empty",
                    "link": data.get("link") or "Empty",
                }

                # Emit signal to Main UI to add to DB
                self.rigAdded.emit(final_name, res_data)

                # Update internal data so we don't re-add / naming collisions in this loop
                self.rig_data[final_name] = res_data
                self.existing_paths[norm_p] = final_name

                count += 1

        # Full refresh to synchronize sections
        self._update_metadata()
        self._refresh_rigs_tab()

        if count > 0:
            QtWidgets.QMessageBox.information(
                self, "AI Batch", "Successfully auto-added {} rigs.".format(count)
            )
        else:
            QtWidgets.QMessageBox.warning(
                self, "AI Batch", "No rigs were added. Check if they were already in the database."
            )

    def _start_scan(self):
        # Always rebuild from current replacements before scanning
        self._rebuild_existing_paths()

        # Create normalized sets for fast, case-consistent lookup
        lookup_existing = set(self.existing_paths.keys())
        lookup_blacklist = set()
        replacements = self._get_replacements()
        for p in self.blacklist:
            # Apply replacements to blacklist paths so scanner can match against local files
            run_p = utils.apply_path_replacements(p, replacements)
            norm_p = utils.normpath_posix_keep_trailing(run_p)
            lookup_blacklist.add(norm_p if sys.platform != "win32" else norm_p.lower())

        self.lbl_scan_prefix.setText("Scanning:")
        self.lbl_scan_prefix.setVisible(True)
        
        # Ensure layout has a chance to calculate before eliding
        self.lbl_scan_path.setVisible(True)
        self.lbl_scan_path.setText("") # Clear first
        QtCore.QTimer.singleShot(0, self._refresh_scanning_path_display)
        
        self.btn_stop_scan.setVisible(True)

        self.worker = ScannerWorker(
        self.directory, lookup_existing, lookup_blacklist, self._get_blocked_paths(), self
    )
        self.worker.fileDiscovered.connect(self._on_file_discovered)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.start()

        # Start searching animation
        self.lbl_loading_dots.start()

    def _refresh_scanning_path_display(self):
        """Helper to force a text update with current elision."""
        if hasattr(self, "lbl_scan_path") and self.lbl_scan_path.isVisible():
            path = self._get_status_path()
            self.lbl_scan_path.setText("<i>{}</i>".format(path))
            self.lbl_scan_path.setToolTip(self.directory)

    def _get_status_path(self):
        """Helper to get elided path for status labels."""
        path = self.directory or ""
        if not path:
            return ""

        # Use QFontMetrics for pixel-perfect elision based on current label width
        metrics = QtGui.QFontMetrics(self.lbl_scan_path.font())
        width = self.lbl_scan_path.width()

        # If width is unknown or too small, estimate from parent dialog width
        if width <= 1:
            # Conservative estimate: Dialog width minus prefix, dots, and stop button
            width = max(50, self.width() - 175)

        return metrics.elidedText(path, QtCore.Qt.ElideLeft, width)

    def _update_discovery_section_dots(self):
        """Reuse the LoadingDotsWidget text in 'Searching...' section text."""
        anim_text = "Scanning{}".format(self.lbl_loading_dots.get_dots_text())
        self.sec_new.set_empty_text(anim_text)

        # Update path label prefix (ensure it's Scanning during the process)
        self.lbl_scan_prefix.setText("Scanning:")

    def _stop_scan(self):
        """Stops the current scan worker."""
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
            path = self._get_status_path()
            self.lbl_scan_prefix.setText("Scanned:")
            self.lbl_scan_path.setText("<i>{}</i>".format(path))
            self.btn_stop_scan.setVisible(False)
            self.lbl_loading_dots.stop()

    def _on_scan_finished(self, any_new):
        """Update status label if nothing was found."""
        self.btn_stop_scan.setVisible(False)
        self.lbl_loading_dots.stop()

        path = self._get_status_path()
        self.lbl_scan_prefix.setText("Scanned:")
        self.lbl_scan_path.setText("<i>{}</i>".format(path))

        if hasattr(self, "sec_new"):
            self.sec_new.set_empty_text("No new rigs found in this directory.")
            if self.sec_new._items:
                self.ai_btn.setEnabled(True)
                self.ai_btn.setToolTip("Auto-tag new rigs with metadata using AI.")

    def _on_file_discovered(self, path, category):
        # Keep track of all files seen this session for fluid UI state changes
        self.session_discovered_paths.add(path)

        # Only add to UI if it's a new rig.
        # Existing and Blacklisted rig widgets are already populated from the whole database.
        if category != "new":
            return

        # Scanner signals paths that EXIST on disk.
        item = ManageRigsItemWidget(path, category, is_found=True, parent=self)
        item.editRequested.connect(self._on_edit_request)
        item.blacklistRequested.connect(self._on_blacklist_request)
        item.whitelistRequested.connect(self._on_whitelist_request)

        self._widgets_map[path] = item
        self.sec_new.addWidget(item)

    def _on_edit_request(self, path):
        # Normalize for database lookup
        norm_p = utils.normpath_posix_keep_trailing(path)
        lookup_p = norm_p if sys.platform != "win32" else norm_p.lower()

        rig_name = self.existing_paths.get(lookup_p)
        mode = "edit" if rig_name else "add"
        rig_data = self.rig_data.get(rig_name) if rig_name else None

        # Determine if this path is an alternative by comparing with the owner's main path
        is_alt = False
        if rig_name and rig_data:
            main_p = rig_data.get("path", "")
            replacements = self._get_replacements()
            run_p = utils.apply_path_replacements(main_p, replacements)
            norm_main = utils.normpath_posix_keep_trailing(run_p)
            lookup_main = norm_main if sys.platform != "win32" else norm_main.lower()
            if lookup_p != lookup_main:
                is_alt = True

        dlg = RigSetupDialog(
            existing_names=list(self.rig_data.keys()),
            collections=self.collections,
            authors=self.authors,
            tags=self.tags,
            mode=mode,
            file_path=path,
            rig_name=rig_name,
            # If it's an alternative, pass empty data to avoid pre-filling with primary info
            rig_data=rig_data if not is_alt else {},
            is_alternative=is_alt,
            parent=self,
        )

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            res = dlg.result_data
            if res:
                if res.get("is_alternative"):
                    target_name = res["name"]
                    old_name = res.get("old_name")

                    # 1. Update target rig with the new alternative
                    target_data = self.rig_data.get(target_name)
                    if target_data:
                        alts = target_data.get("alternatives", [])
                        if path not in alts:
                            alts.append(path)
                            target_data["alternatives"] = alts
                            self.rigAdded.emit(target_name, target_data)

                    # 2. Handle old association
                    if old_name and old_name in self.rig_data and old_name != target_name:
                        old_data = self.rig_data[old_name]
                        # Normalize for safe comparison
                        old_main_p = utils.normpath_posix_keep_trailing(old_data.get("path", ""))
                        current_p = utils.normpath_posix_keep_trailing(path)

                        if old_main_p == current_p:
                            del self.rig_data[old_name]
                            self.rigAdded.emit(old_name, {})
                        else:
                            # It was an alternative, remove from old owner list
                            alts = old_data.get("alternatives", [])
                            # Normalize the alternatives list for lookup
                            norm_alts = [utils.normpath_posix_keep_trailing(a) for a in alts]
                            if current_p in norm_alts:
                                idx = norm_alts.index(current_p)
                                alts.pop(idx)
                                old_data["alternatives"] = alts
                                self.rigAdded.emit(old_name, old_data)

                    self.existing_paths[lookup_p] = target_name
                else:
                    self.rigAdded.emit(res["name"], res["data"])
                    self.rig_data[res["name"]] = res["data"]
                    self.existing_paths[lookup_p] = res["name"]

                # Move/Update widget
                item = self._widgets_map.get(path)
                if item:
                    if item.category == "new":
                        self.sec_new.removeWidget(item)
                        item.set_category("exists")
                        self.sec_exists.addWidget(item)
                    item.set_added()

                # Full refresh to ensure consistency (like removing old main entries from UI)
                self._update_metadata()
                self._refresh_rigs_tab()

    def _update_metadata(self):
        """Re-scans self.rig_data to update unique collections, authors, and tags."""
        collections = set()
        authors = set()
        tags = set()

        for name, data in self.rig_data.items():
            if name.startswith("_"):
                continue

            c = data.get("collection")
            if c and c != "Empty":
                collections.add(c)

            a = data.get("author")
            if a and a != "Empty":
                authors.add(a)

            ts = data.get("tags", [])
            if ts:
                tags.update(ts)

        self.collections = sorted(list(collections))
        self.authors = sorted(list(authors))
        self.tags = sorted(list(tags))

    def _on_remove_request(self, path):
        # Normalize for database lookup
        curr_p = utils.normpath_posix_keep_trailing(path)
        lookup_p = curr_p if sys.platform != "win32" else curr_p.lower()

        rig_name = self.existing_paths.get(lookup_p)
        if not rig_name:
            return

        msg = "Are you sure you want to remove '{}' from the database?\n\nThis will NOT delete the file from your computer.".format(
            rig_name
        )
        if (
            QtWidgets.QMessageBox.question(
                self, "Remove Rig", msg, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            == QtWidgets.QMessageBox.No
        ):
            return

        rig_data = self.rig_data.get(rig_name)
        if rig_data:
            main_p = utils.normpath_posix_keep_trailing(rig_data.get("path", ""))
            # Use original system logic for cross-platform matching
            match_p = main_p if sys.platform != "win32" else main_p.lower()

            if match_p == lookup_p:
                # Removing the MAIN rig entry
                del self.rig_data[rig_name]
                self.rigAdded.emit(rig_name, {})
            else:
                # Removing an ALTERNATIVE from its owner
                alts = rig_data.get("alternatives", [])
                norm_alts = [utils.normpath_posix_keep_trailing(a) for a in alts]
                if curr_p in norm_alts:
                    idx = norm_alts.index(curr_p)
                    alts.pop(idx)
                    rig_data["alternatives"] = alts
                    self.rigAdded.emit(rig_name, rig_data)

        self._update_metadata()
        self._refresh_rigs_tab()

    def _on_blacklist_request(self, path):
        norm_path = utils.normpath_posix_keep_trailing(path)
        if norm_path not in self.blacklist:
            self.blacklist.append(norm_path)
            self.blacklistChanged.emit(self.blacklist)

            # Ensure blacklist section is visible if we just added something
            self.sec_black.btn.setChecked(True)

        # Trigger a full tab refresh to move the item correctly and handle category changes
        self._refresh_rigs_tab()

    def _on_whitelist_request(self, path):
        norm_path = utils.normpath_posix_keep_trailing(path)
        if norm_path in self.blacklist:
            self.blacklist.remove(norm_path)
            self.blacklistChanged.emit(self.blacklist)

        # Trigger a full tab refresh to move the item back to its correct section
        self._refresh_rigs_tab()
