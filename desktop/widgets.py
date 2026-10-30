from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QStyle, QStyledItemDelegate, QWidget

from .library import STATUS, explanation, height_text

COLORS = {"pending": "#64766e", "measured": "#17675a", "uncertain": "#925c13", "unusable": "#9a4d4d", "error": "#9a4d4d"}
BACKGROUNDS = {"pending": "#edf1ed", "measured": "#e3f2e9", "uncertain": "#fbefd7", "unusable": "#f7e9e7", "error": "#f7e9e7"}


class ImageTable(QAbstractTableModel):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.active_row = -1

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ["Bilddatei", "Höhe", "Ergebnis"][section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        result = row["result"]
        status = result["status"] if result else "pending"
        if role == Qt.ItemDataRole.DisplayRole:
            height = height_text(result)
            return [Path(row["path"]).name, height + (" cm" if height != "—" else ""), "Wird ausgewertet" if index.row() == self.active_row else STATUS[status]][index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return row["path"] if index.column() == 0 else explanation(result)
        if role == Qt.ItemDataRole.UserRole:
            return status
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        text = index.data()
        status = index.data(Qt.ItemDataRole.UserRole)
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#e8f1eb"))
        painter.setFont(option.font)
        width = min(option.rect.width() - 12, option.fontMetrics.horizontalAdvance(text) + 18)
        box = QRectF(option.rect.left() + 6, option.rect.center().y() - 12, width, 24)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BACKGROUNDS[status]))
        painter.drawRoundedRect(box, 5, 5)
        painter.setPen(QColor(COLORS[status]))
        painter.drawText(box.adjusted(9, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter,
                         option.fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight, int(width - 16)))
        painter.restore()


class ResultFilter(QSortFilterProxyModel):
    mode = 0
    search = ""

    def filterAcceptsRow(self, row, parent):
        record = self.sourceModel().rows[row]
        status = record["result"]["status"] if record["result"] else "pending"
        category = self.mode == 0 or (self.mode == 1 and status == "measured") or (self.mode == 2 and status in {"uncertain", "unusable", "error"}) or (self.mode == 3 and status == "pending")
        return category and self.search in Path(record["path"]).name.casefold()


class HeightChart(QWidget):
    selected = Signal(int)

    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.selected_row = -1
        self.setMinimumHeight(74)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Schneehöhen in der Bildfolge. Ein Klick öffnet das zugehörige Originalbild.")

    def chart_box(self):
        return QRectF(37, 8, max(1, self.width() - 53), max(1, self.height() - 33))

    def row_at(self, position):
        points = [i for i, row in enumerate(self.rows) if row["result"] and row["result"]["status"] == "measured"]
        if not points:
            return None
        box = self.chart_box()
        expected = (position.x() - box.left()) / box.width() * (len(self.rows) - 1)
        return min(points, key=lambda i: abs(i - expected))

    def mousePressEvent(self, event):
        index = self.row_at(event.position())
        if index is not None:
            self.selected.emit(index)

    def mouseMoveEvent(self, event):
        index = self.row_at(event.position())
        if index is not None:
            row = self.rows[index]
            self.setToolTip(f"Bild {index + 1} · {Path(row['path']).name}\n{height_text(row['result'])} cm · Klicken zum Ansehen")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = self.chart_box()
        points = [(i, row["result"]["snow_height_cm"]) for i, row in enumerate(self.rows) if row["result"] and row["result"]["status"] == "measured"]
        maximum = max(10, math.ceil(max((h for _, h in points), default=0) / 10) * 10)
        painter.setFont(QFont("Segoe UI", 9))
        for step in range(3):
            y = box.bottom() - box.height() * step / 2
            painter.setPen(QColor("#e4e9e2"))
            painter.drawLine(box.left(), y, box.right(), y)
            painter.setPen(QColor("#68776e"))
            painter.drawText(QRectF(0, y - 10, 29, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{maximum * step / 2:g}")
        if not points:
            painter.setPen(QColor("#68776e"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "Die gemessenen Schneehöhen erscheinen hier.")
            return
        def x_for(i):
            return box.center().x() if len(self.rows) == 1 else box.left() + i / (len(self.rows) - 1) * box.width()
        if self.selected_row >= 0:
            painter.setPen(QPen(QColor("#b4c8b9"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(x_for(self.selected_row), box.top(), x_for(self.selected_row), box.bottom())
        for i, value in points:
            radius = 4 if i == self.selected_row else 2.5
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#123e32" if i == self.selected_row else "#438a70"))
            painter.drawEllipse(QRectF(x_for(i) - radius, box.bottom() - value / maximum * box.height() - radius, radius * 2, radius * 2))
        painter.setPen(QColor("#68776e"))
        painter.drawText(QRectF(box.left(), box.bottom() + 5, box.width(), 20), Qt.AlignmentFlag.AlignLeft, "Bild 1")
        if len(self.rows) > 1:
            painter.drawText(QRectF(box.left(), box.bottom() + 5, box.width(), 20), Qt.AlignmentFlag.AlignRight, f"Bild {len(self.rows)}")


class ImagePreview(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName("Originalbild. Mausrad zum Zoomen, Ziehen zum Verschieben.")
        self.item = None
        self.path = None
        self.fitted_transform = None

    def show_file(self, path):
        if self.path == path:
            return self.item is not None
        self.path = path
        self.scene().clear()
        self.item = None
        if not path:
            return False
        size = QImageReader(path).size()
        if (size.width(), size.height()) != (1920, 1080):
            return False
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        self.item = self.scene().addPixmap(pixmap)
        self.scene().setSceneRect(self.item.boundingRect())
        self.fit()
        return True

    def fit(self):
        if self.item:
            self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)
            self.fitted_transform = self.transform()

    def resizeEvent(self, event):
        was_fitted = self.transform() == self.fitted_transform
        super().resizeEvent(event)
        # A user-controlled zoom stays authoritative when layout or scrollbars change.
        if was_fitted:
            self.fit()

    def zoom(self, factor):
        if self.item:
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
