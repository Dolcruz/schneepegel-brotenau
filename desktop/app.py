from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSortFilterProxyModel, Qt, QStandardPaths
from PySide6.QtGui import QColor, QFont, QIcon, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from .library import Library, STATUS, explanation, export_csv, height_text
from .worker import AnalysisWorker


COLORS = {"pending": "#687a86", "measured": "#167166", "uncertain": "#98621b", "unusable": "#9b5360", "error": "#9b5360"}
STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #233c4b; }
QMainWindow, QWidget#page { background: #f3f6f7; }
QFrame#rail { background: #173b4d; border: none; }
QFrame#rail QLabel { color: #d3e2e9; background: transparent; }
QLabel#brand { color: #ffffff; font-size: 18pt; font-weight: 700; }
QLabel#railSection { color: #9eb8c5; font-size: 9pt; }
QLabel#railActive { background: #285061; color: #ffffff; border-radius: 6px; padding: 12px; font-weight: 600; }
QLabel#title { font-size: 24pt; font-weight: 650; color: #18394a; }
QLabel#muted { color: #667b88; }
QFrame#card { background: white; border: 1px solid #dde5e9; border-radius: 9px; }
QLabel#metric { font-size: 25pt; font-weight: 650; }
QLabel#section { font-size: 12pt; font-weight: 650; }
QLabel#hero { font-size: 22pt; font-weight: 650; }
QLabel#hint { color: #657b88; font-size: 9pt; }
QPushButton { background: white; border: 1px solid #cddae1; border-radius: 6px; padding: 10px 16px; font-weight: 600; min-height: 22px; }
QPushButton:hover { background: #eaf1f4; border-color: #8daab8; }
QPushButton:pressed { background: #dce8ed; }
QPushButton:focus { border: 2px solid #3e8fa5; }
QPushButton:disabled { background: #edf1f3; color: #92a1aa; border-color: #dfe6e9; }
QPushButton#primary { background: #196d77; border-color: #196d77; color: white; }
QPushButton#primary:hover { background: #115d66; }
QPushButton#primary:pressed { background: #0b4c54; }
QPushButton#primary:disabled { background: #b3c8cd; border-color: #b3c8cd; color: #f5f8f9; }
QPushButton#quiet { background: transparent; padding: 6px 10px; }
QComboBox { background: white; border: 1px solid #cddae1; border-radius: 6px; padding: 9px 12px; min-width: 130px; }
QTableView { background: white; alternate-background-color: #f7fafb; border: none; gridline-color: #edf1f3; selection-background-color: #dfedf1; selection-color: #173b4d; }
QTableView::item { padding: 10px; border-bottom: 1px solid #edf1f3; }
QTableView::item:focus { border: 1px solid #3e8fa5; }
QHeaderView::section { background: #f7fafb; color: #607783; border: none; border-bottom: 1px solid #dde5e9; padding: 11px; font-weight: 600; }
QProgressBar { border: none; background: #e3ecef; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: #207e87; border-radius: 3px; }
QGraphicsView { border: none; background: #e9eff2; }
QSplitter::handle { background: transparent; width: 16px; }
QToolTip { background: #173b4d; color: white; border: none; padding: 6px; }
"""


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, action, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(action)
    return widget


def card():
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return widget, layout


class ImageTable(QAbstractTableModel):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ["Nr.", "Bilddatei", "Schneehöhe", "Ergebnis"][section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        result = row["result"]
        status = result["status"] if result else "pending"
        if role == Qt.ItemDataRole.DisplayRole:
            height = height_text(result)
            return [str(index.row() + 1), Path(row["path"]).name, height + (" cm" if height != "—" else ""), STATUS[status]][index.column()]
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 3:
            return QColor(COLORS[status])
        if role == Qt.ItemDataRole.ToolTipRole:
            return row["path"] if index.column() == 1 else explanation(result)
        if role == Qt.ItemDataRole.UserRole:
            return status


class ResultFilter(QSortFilterProxyModel):
    mode = 0

    def filterAcceptsRow(self, row, parent):
        result = self.sourceModel().rows[row]["result"]
        status = result["status"] if result else "pending"
        return self.mode == 0 or (self.mode == 1 and status == "measured") or (self.mode == 2 and status in {"uncertain", "unusable", "error"}) or (self.mode == 3 and status == "pending")


class HeightChart(QWidget):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.setMinimumHeight(100)
        self.setAccessibleName("Schneehöhen nach Bildnummer. Nur freigegebene Messungen werden dargestellt.")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(40, 12, self.width() - 56, self.height() - 38)
        points = [(i, r["result"]["snow_height_cm"]) for i, r in enumerate(self.rows) if r["result"] and r["result"]["status"] == "measured"]
        maximum = max(10, math.ceil(max((h for _, h in points), default=0) / 10) * 10)
        painter.setFont(QFont("Segoe UI", 9))
        for step in range(3):
            y = box.bottom() - box.height() * step / 2
            painter.setPen(QColor("#e5ecef"))
            painter.drawLine(box.left(), y, box.right(), y)
            painter.setPen(QColor("#6b818d"))
            painter.drawText(QRectF(0, y - 10, 32, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{maximum * step / 2:g}")
        if not points:
            painter.setPen(QColor("#728692"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "Ihre Messwerte erscheinen hier nach der Analyse.")
            return
        painter.setPen(QPen(QColor("#1d7a82"), 2))
        painter.setBrush(QColor("#1d7a82"))
        for i, value in points:
            x = box.center().x() if len(self.rows) == 1 else box.left() + i / (len(self.rows) - 1) * box.width()
            y = box.bottom() - value / maximum * box.height()
            painter.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
        painter.setPen(QColor("#6b818d"))
        painter.drawText(QRectF(box.left(), box.bottom() + 6, box.width(), 20), Qt.AlignmentFlag.AlignLeft, "Bild 1")
        if len(self.rows) > 1:
            painter.drawText(QRectF(box.left(), box.bottom() + 6, box.width(), 20), Qt.AlignmentFlag.AlignRight, f"Bild {len(self.rows)}")


class ImagePreview(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName("Originalbild. Mit dem Mausrad zoomen, mit gedrückter Maustaste verschieben.")
        self.item = None

    def show_file(self, path):
        self.scene().clear()
        self.item = None
        size = QImageReader(path).size()
        if (size.width(), size.height()) != (1920, 1080):
            return False
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.item = self.scene().addPixmap(pixmap)
            self.scene().setSceneRect(self.item.boundingRect())
            self.fit()
            return True
        return False

    def fit(self):
        if self.item:
            self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def wheelEvent(self, event):
        self.scale(1.2 if event.angleDelta().y() > 0 else 1 / 1.2, 1.2 if event.angleDelta().y() > 0 else 1 / 1.2)


class MainWindow(QMainWindow):
    def __init__(self, storage: Path):
        super().__init__()
        self.library = Library(storage)
        self.worker = None
        self.closing = False
        self.finished_count = 0
        self.run_error = False
        self.setWindowTitle("Schneepegel · Brotenau")
        self.resize(1340, 900)
        self.setMinimumSize(1000, 720)
        self.setAcceptDrops(True)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(200)
        side = QVBoxLayout(rail)
        side.setContentsMargins(22, 32, 22, 24)
        side.setSpacing(16)
        side.addWidget(label("❄", "brand"))
        side.addWidget(label("Schneepegel", "brand"))
        side.addWidget(label("BROTENAU", "railSection"))
        side.addSpacing(30)
        side.addWidget(label("◉   Bildauswertung", "railActive"))
        side.addStretch()
        side.addWidget(label("LOKALE AUSWERTUNG", "railSection"))
        side.addWidget(label("Ihre Bilder bleiben\nauf diesem Computer.", wrap=True))
        side.addSpacing(14)
        side.addWidget(label("Station Brotenau\nKalibrierte Kamera · 1920 × 1080", "railSection", True))
        shell.addWidget(rail)
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 20)
        layout.setSpacing(18)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.addWidget(label("Schnee sichtbar. Höhe messbar.", "title", True))
        headings.addWidget(label("Stationsbilder auswerten und Messwerte im Blick behalten.", "muted"))
        header.addLayout(headings, 1)
        help_button = button("Hilfe", self.help)
        help_button.setObjectName("quiet")
        header.addWidget(help_button)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        self.add_button = button("＋  Bilder hinzufügen", self.choose_files)
        self.folder_button = button("Ordner auswählen", self.choose_folder)
        self.start_button = button("Analyse starten", self.start_analysis, True)
        self.stop_button = button("Anhalten", self.stop_analysis)
        self.stop_button.hide()
        self.export_button = button("CSV exportieren", self.export)
        for widget in (self.add_button, self.folder_button, self.start_button, self.stop_button):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        toolbar.addWidget(self.export_button)
        layout.addLayout(toolbar)

        self.metrics = []
        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        for title, color in [("Bilder insgesamt", "#233c4b"), ("Erfolgreich gemessen", "#167166"), ("Bitte ansehen", "#98621b"), ("Höchster Messwert", "#233c4b")]:
            frame, content = card()
            content.addWidget(label(title, "muted", True))
            value = label("—", "metric")
            value.setStyleSheet(f"color: {color}")
            content.addWidget(value)
            metrics.addWidget(frame)
            self.metrics.append(value)
        layout.addLayout(metrics)

        chart_card, chart_layout = card()
        chart_head = QHBoxLayout()
        chart_head.addWidget(label("Schneehöhen im Überblick", "section"))
        chart_head.addStretch()
        chart_head.addWidget(label("●  Gemessene Höhe in cm", "hint"))
        chart_layout.addLayout(chart_head)
        self.chart = HeightChart(self.library.rows)
        chart_layout.addWidget(self.chart)
        chart_layout.addWidget(label("Reihenfolge der importierten Bilder · Unsichere Ergebnisse bleiben ohne Messpunkt.", "hint", True))
        layout.addWidget(chart_card)

        self.body = QStackedWidget()
        empty, empty_layout = card()
        empty_layout.addStretch()
        title = label("Der nächste Winter kann kommen.", "hero")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(title)
        hint = label("Ziehen Sie Ihre Stationsbilder hierher oder wählen Sie einen Bildordner.\nDanach genügt ein Klick auf „Analyse starten“.", "muted", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(hint)
        empty_layout.addStretch()
        self.body.addWidget(empty)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setMinimumHeight(320)
        results_card, results_layout = card()
        results_layout.setContentsMargins(0, 16, 0, 0)
        table_head = QHBoxLayout()
        table_head.setContentsMargins(16, 0, 16, 0)
        table_head.addWidget(label("Ihre Bilder", "section"))
        table_head.addStretch()
        self.filter = QComboBox()
        self.filter.setAccessibleName("Ergebnisse filtern")
        self.filter.addItems(["Alle Ergebnisse", "Gemessen", "Bitte ansehen", "Noch offen"])
        self.filter.currentIndexChanged.connect(self.set_filter)
        table_head.addWidget(self.filter)
        results_layout.addLayout(table_head)
        self.table = QTableView()
        self.table.setAccessibleName("Importierte Bilder und Analyseergebnisse")
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.model = ImageTable(self.library.rows)
        self.proxy = ResultFilter()
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in [(0, 48), (2, 115), (3, 145)]:
            self.table.setColumnWidth(column, width)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        results_layout.addWidget(self.table)
        splitter.addWidget(results_card)

        preview_card, preview_layout = card()
        preview_layout.setContentsMargins(16, 12, 16, 12)
        preview_layout.setSpacing(6)
        preview_head = QHBoxLayout()
        preview_head.addWidget(label("Original & Ergebnis", "section"))
        preview_head.addStretch()
        self.preview = ImagePreview()
        zoom = button("Einpassen", self.preview.fit)
        zoom.setObjectName("quiet")
        zoom.setToolTip("Mausrad: zoomen · Ziehen: Bild verschieben")
        preview_head.addWidget(zoom)
        preview_layout.addLayout(preview_head)
        self.preview.setMinimumHeight(96)
        preview_layout.addWidget(self.preview, 1)
        self.file_label = label("Wählen Sie links ein Bild aus.", "hint", True)
        preview_layout.addWidget(self.file_label)
        self.result_label = label("—", "hero")
        self.result_label.setStyleSheet("font-size: 18pt;")
        preview_layout.addWidget(self.result_label)
        self.reason_label = label("", "muted", True)
        preview_layout.addWidget(self.reason_label)
        splitter.addWidget(preview_card)
        splitter.setSizes([650, 350])
        self.body.addWidget(splitter)
        layout.addWidget(self.body, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        footer = QHBoxLayout()
        self.message = label("Bereit. Bilder hinzufügen und die Analyse starten.", "hint")
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.message, 1)
        self.clear_button = button("Liste leeren", self.clear)
        self.clear_button.setObjectName("quiet")
        footer.addWidget(self.clear_button)
        right = QWidget()
        right.setObjectName("page")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        right_layout.addWidget(scroll, 1)
        footer_area = QWidget()
        footer_layout = QVBoxLayout(footer_area)
        footer_layout.setContentsMargins(30, 0, 30, 12)
        footer_layout.addWidget(self.progress)
        footer_layout.addLayout(footer)
        right_layout.addWidget(footer_area)
        shell.addWidget(right, 1)
        self.refresh()
        if self.library.rows:
            self.table.selectRow(0)

    def refresh(self):
        rows = self.library.rows
        results = [row["result"] for row in rows if row["result"]]
        measured = [r for r in results if r["status"] == "measured"]
        for widget, value in zip(self.metrics, [str(len(rows)), str(len(measured)), str(len(results) - len(measured)), (f'{max(r["snow_height_cm"] for r in measured):g}'.replace(".", ",") + " cm") if measured else "—"]):
            widget.setText(value)
        self.body.setCurrentIndex(1 if rows else 0)
        self.chart.update()
        busy = self.worker is not None
        self.start_button.setEnabled(not busy and any(r["result"] is None for r in rows))
        self.export_button.setEnabled(bool(results))
        self.clear_button.setEnabled(bool(rows) and not busy)
        self.add_button.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Stationsbilder auswählen", "", "Stationsbilder (*.jpg *.jpeg *.png)")
        if files:
            self.add_paths([Path(f) for f in files])

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Bildordner auswählen")
        if folder:
            self.add_paths(sorted(p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}))

    def add_paths(self, paths):
        if self.worker:
            return
        self.model.beginResetModel()
        try:
            count = self.library.add(paths)
        except (OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Bilder nicht hinzugefügt", str(exc))
            count = 0
        finally:
            self.model.endResetModel()
        self.message.setText(f"{count} Bilder hinzugefügt. Originaldateien bleiben an ihrem Speicherort.")
        self.refresh()
        if self.proxy.rowCount():
            self.table.selectRow(0)

    def set_filter(self, mode):
        self.proxy.mode = mode
        self.proxy.invalidateFilter()
        self.selection_changed()

    def selection_changed(self, *_):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            self.preview.scene().clear()
            self.preview.item = None
            self.file_label.setText("Wählen Sie links ein Bild aus.")
            self.result_label.setText("—")
            self.reason_label.setText("")
            return
        row = self.library.rows[self.proxy.mapToSource(selected[0]).row()]
        available = self.preview.show_file(row["path"])
        self.file_label.setText(Path(row["path"]).name)
        result = row["result"]
        status = result["status"] if result else "pending"
        self.result_label.setStyleSheet(f"font-size: 18pt; color: {COLORS[status]}")
        self.result_label.setText(height_text(result) + " cm" if status == "measured" else STATUS[status])
        self.reason_label.setText(explanation(result) + ("\n\nKeine Vorschau: Datei fehlt oder ist kein unterstütztes Stationsbild." if not available else ""))

    def start_analysis(self):
        jobs = [(i, r["path"]) for i, r in enumerate(self.library.rows) if r["result"] is None]
        if not jobs or self.worker:
            return
        self.finished_count = 0
        self.run_error = False
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.progress.show()
        self.message.setText("Analyse wird vorbereitet. Die Modelle werden lokal geladen …")
        self.worker = AnalysisWorker(jobs, self)
        self.worker.current.connect(self.on_current)
        self.worker.result.connect(self.on_result)
        self.worker.failed.connect(self.on_failure)
        self.worker.finished.connect(self.on_finished)
        self.start_button.hide()
        self.stop_button.show()
        self.stop_button.setEnabled(True)
        self.refresh()
        self.worker.start()

    def on_current(self, index, name):
        self.message.setText(f"Bild {self.finished_count + 1} von {self.progress.maximum()}: {name}")

    def on_result(self, index, result):
        try:
            self.library.save_result(index, result)
        except Exception as exc:
            self.run_error = True
            self.worker.requestInterruption()
            QMessageBox.critical(self, "Ergebnis konnte nicht gespeichert werden", str(exc))
            return
        self.model.dataChanged.emit(self.model.index(index, 0), self.model.index(index, 3))
        self.finished_count += 1
        self.progress.setValue(self.finished_count)
        self.refresh()
        self.selection_changed()

    def on_failure(self, message):
        self.run_error = True
        QMessageBox.critical(self, "Analyse nicht verfügbar", message)

    def stop_analysis(self):
        if self.worker:
            self.worker.requestInterruption()
            self.stop_button.setEnabled(False)
            self.message.setText("Wird nach dem laufenden Bild angehalten. Ergebnisse bleiben gespeichert.")

    def on_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.start_button.show()
        self.stop_button.hide()
        self.progress.hide()
        self.message.setText(
            f"Analyse mit Fehler beendet. {self.finished_count} Ergebnisse gespeichert."
            if self.run_error else
            f"{self.finished_count} Bilder ausgewertet. Ergebnisse sind auf diesem Computer gespeichert."
        )
        self.refresh()
        if self.closing:
            self.close()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Ergebnisse exportieren", "Schneepegel_Brotenau.csv", "CSV-Tabelle (*.csv)")
        if path:
            try:
                export_csv(Path(path), self.library.rows)
            except OSError as exc:
                QMessageBox.warning(self, "Export nicht möglich", str(exc))
            else:
                self.message.setText("CSV gespeichert. Sie können die Tabelle direkt in Excel öffnen.")

    def clear(self):
        if QMessageBox.question(self, "Liste leeren?", "Bildliste und gespeicherte Ergebnisse aus dieser App entfernen? Ihre Originalbilder bleiben erhalten.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.model.beginResetModel()
            self.library.clear()
            self.model.endResetModel()
            self.selection_changed()
            self.refresh()

    def help(self):
        QMessageBox.information(self, "So funktioniert die Auswertung", "1. Bilder hinzufügen oder einen Bildordner auswählen. Unterordner werden einbezogen.\n2. Analyse starten.\n3. Ergebnisse prüfen und bei Bedarf als CSV exportieren.\n\nGemessen: freigegebener Messwert.\nBitte prüfen: keine ausreichend sichere Messung.\nNicht auswertbar: Bildqualität reicht nicht aus.\nDateifehler: Datei fehlt oder passt nicht zum erwarteten Bildformat.\n\nKlicken Sie auf ein Bild für die Originalansicht. Mausrad: zoomen; Ziehen: verschieben.\n\nDie Auswertung ist ausschließlich für die kalibrierte Kamera in Brotenau und JPG/PNG mit 1920 × 1080 Pixeln vorgesehen. Reale Trainingsdaten über 25 cm fehlen bisher; größere Höhen wurden überwiegend synthetisch geprüft.\n\nDie Grafik zeigt die Importreihenfolge, keine Zeitachse. Datum und Uhrzeit bleiben im Originalbild erhalten und werden nicht automatisch ausgelesen. Ergebnisse werden lokal gespeichert, Originalbilder nicht kopiert.\n\nAnhalten wirkt nach dem laufenden Bild. Die Analyse läuft ohne Zeitlimit und ohne automatische Wiederholungen. Ein Bild gleichzeitig; PyTorch und numerische Bibliotheken: 2 CPU-Threads, OpenCV: 1, PyTorch Interop: 1, Regressoren: je 1 Worker. SQLite: 5 Sekunden Wartezeit bei Dateisperren.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.worker:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                paths.extend(sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}))
            elif path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                paths.append(path)
        self.add_paths(paths)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.worker:
            self.closing = True
            self.stop_analysis()
            self.message.setText("Die App schließt nach dem laufenden Bild. Ergebnisse bleiben gespeichert.")
            event.ignore()
        else:
            self.library.close()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Schneepegel Brotenau")
    app.setOrganizationName("Brotenau")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    icon_path = Path(__file__).parent / "app.ico"
    app.setWindowIcon(QIcon(str(icon_path)))
    storage = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "ergebnisse.sqlite3"
    try:
        window = MainWindow(storage)
    except Exception as exc:
        QMessageBox.critical(None, "Schneepegel konnte nicht geöffnet werden", f"Die gespeicherten Ergebnisse konnten nicht geöffnet werden.\n\n{exc}")
        return 1
    window.show()
    return app.exec()
