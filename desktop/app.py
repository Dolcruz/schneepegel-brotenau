from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSplitter, QStackedWidget, QTableView, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from .library import Library, STATUS, explanation, export_csv, height_text
from .widgets import BACKGROUNDS, COLORS, HeightChart, ImagePreview, ImageTable, ResultFilter, StatusDelegate
from .worker import AnalysisWorker


STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #253c31; }
QMainWindow, QWidget#shell { background: #f4f6f0; }
QLabel { background: transparent; }
QLabel#brand { font-size: 17pt; font-weight: 650; color: #203c2e; }
QLabel#eyebrow { font-size: 8pt; font-weight: 600; color: #647368; }
QLabel#muted { color: #65746b; }
QLabel#caption { font-size: 9pt; color: #65746b; }
QLabel#section { font-size: 11pt; font-weight: 650; }
QLabel#emptyTitle { font-size: 28pt; font-weight: 650; color: #203c2e; }
QLabel#emptyText { font-size: 12pt; color: #647368; }
QLabel#height { font-size: 22pt; font-weight: 650; color: #17675a; }
QLabel#badge { padding: 5px 10px; border-radius: 5px; font-size: 9pt; font-weight: 600; }
QLabel#local { color: #46715a; background: #e7eee2; border-radius: 5px; padding: 6px 10px; font-size: 9pt; }
QFrame#panel { background: #ffffff; border: 1px solid #dce3d9; border-radius: 8px; }
QFrame#line { background: #dce3d9; max-height: 1px; border: none; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #cbd5c9; border-radius: 6px; padding: 9px 14px; min-height: 22px; font-weight: 600; }
QPushButton:hover, QToolButton:hover { background: #eaf1e7; border-color: #8ca38e; }
QPushButton:pressed, QToolButton:pressed { background: #dce9dd; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus { border: 2px solid #438a70; }
QPushButton:disabled, QToolButton:disabled { background: #f3f5f1; border-color: #e3e8de; color: #96a296; }
QPushButton#primary { background: #275c43; border-color: #275c43; color: white; }
QPushButton#primary:hover { background: #1d4c35; }
QPushButton#primary:pressed { background: #153d29; }
QPushButton#primary:disabled { background: #a9bcad; border-color: #a9bcad; }
QPushButton#quiet { background: transparent; border-color: transparent; font-weight: 400; padding: 6px 10px; }
QPushButton#quiet:hover { background: #e9eee4; border-color: #d6e0d1; }
QPushButton#filter { background: transparent; border-color: transparent; color: #65746b; padding: 8px 12px; }
QPushButton#filter:checked { background: #e1eddd; border-color: #c8dac2; color: #264d35; }
QPushButton#filter:hover { background: #e9eee4; }
QLineEdit { background: #ffffff; border: 1px solid #cbd5c9; border-radius: 6px; padding: 9px 10px; min-height: 22px; selection-background-color: #d6e6d2; }
QTableView { background: white; alternate-background-color: #fafbf8; border: none; selection-background-color: #e8f1eb; selection-color: #203c2e; }
QTableView::item { padding: 10px 8px; border-bottom: 1px solid #edf0e9; }
QTableView::item:focus { border: 1px solid #9db7a6; }
QHeaderView::section { background: #f7f9f4; color: #65746b; border: none; border-bottom: 1px solid #dce3d9; padding: 10px 8px; font-weight: 600; }
QProgressBar { border: none; background: #e0e8db; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #438a70; border-radius: 3px; }
QGraphicsView { border: 1px solid rgba(0,0,0,0.1); background: #172920; }
QLabel#noPreview { background: #172920; color: #dbe6d9; padding: 24px; border-radius: 5px; }
QSplitter::handle { background: #f4f6f0; }
QSplitter::handle:hover { background: #d9e4d3; }
QMenu { background: white; border: 1px solid #dce3d9; padding: 6px; }
QMenu::item { padding: 8px 18px; border-radius: 4px; }
QMenu::item:selected { background: #e8f1e3; }
QTabWidget::pane { border: none; background: white; }
QTabBar::tab { color: #65746b; padding: 10px 18px; border-bottom: 2px solid #e5eade; }
QTabBar::tab:selected { color: #275c43; border-bottom: 2px solid #438a70; font-weight: 600; }
QTabBar::tab:hover { background: #f3f7ee; }
QToolTip { background: #243e30; color: white; padding: 7px; border: none; }
"""


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, action, name=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(action)
    return widget


def panel():
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(10)
    return frame, layout


class MainWindow(QMainWindow):
    def __init__(self, storage: Path):
        super().__init__()
        self.library = Library(storage)
        self.worker = None
        self.closing = False
        self.finished_count = 0
        self.run_error = False
        self.stopping = False
        self.jobs_total = 0
        self.current_row = -1
        self.setWindowTitle("Schneepegel Brotenau")
        self.setMinimumSize(1000, 700)
        self.resize(1400, 920)
        self.setAcceptDrops(True)
        root = QWidget()
        root.setObjectName("shell")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 18, 24, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(Path(__file__).parent / "app.ico")).pixmap(40, 40))
        header.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(1)
        names.addWidget(label("Schneepegel Brotenau", "brand"))
        names.addWidget(label("STATIONSBILDER AUSWERTEN", "eyebrow"))
        header.addLayout(names)
        header.addStretch()
        header.addWidget(label("Lokal auf diesem Computer", "local"))
        header.addWidget(button("Hilfe", self.help, "quiet"))
        layout.addLayout(header)

        self.toolbar = QWidget()
        actions = QHBoxLayout(self.toolbar)
        actions.setContentsMargins(0, 0, 0, 0)
        self.add_button = button("Bilder hinzufügen", self.choose_files, "primary")
        self.folder_button = button("Ordner auswählen", self.choose_folder)
        self.start_button = button("Auswertung fortsetzen", self.start_analysis)
        self.stop_button = button("Anhalten", self.stop_analysis)
        self.export_button = button("Für Excel exportieren", self.export)
        for control in (self.add_button, self.folder_button, self.start_button, self.stop_button):
            actions.addWidget(control)
        actions.addStretch()
        actions.addWidget(self.export_button)
        self.more_button = QToolButton()
        self.more_button.setText("Mehr")
        self.more_button.setAccessibleName("Weitere Aktionen")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        self.remove_action = menu.addAction("Ausgewähltes Bild aus der Liste entfernen", self.remove_selected)
        self.clear_action = menu.addAction("Gesamte Bildliste leeren", self.clear)
        self.more_button.setMenu(menu)
        actions.addWidget(self.more_button)
        layout.addWidget(self.toolbar)

        self.body = QStackedWidget()
        empty, empty_layout = panel()
        empty_layout.addStretch()
        empty_logo = QLabel()
        empty_logo.setPixmap(QIcon(str(Path(__file__).parent / "app.ico")).pixmap(72, 72))
        empty_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_logo)
        title = label("Wie hoch liegt der Schnee?", "emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(title)
        description = label("Wählen Sie Ihre Stationsbilder oder ziehen Sie einen Ordner in dieses Fenster.\nDie Bilder werden anschließend automatisch ausgewertet.", "emptyText", True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(description)
        empty_layout.addSpacing(16)
        empty_actions = QHBoxLayout()
        empty_actions.addStretch()
        empty_actions.addWidget(button("Bilder auswählen", self.choose_files, "primary"))
        empty_actions.addWidget(button("Ordner auswählen", self.choose_folder))
        empty_actions.addStretch()
        empty_layout.addLayout(empty_actions)
        empty_layout.addSpacing(24)
        steps = label("1  Bilder hinzufügen     ·     2  Ergebnisse ansehen     ·     3  Tabelle exportieren", "muted")
        steps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(steps)
        empty_layout.addStretch()
        context = label("Für die Kamera am Schneepegel Brotenau · JPG/PNG mit 1920 × 1080 Pixeln", "caption")
        context.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(context)
        self.body.addWidget(empty)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(10)
        filters = QHBoxLayout()
        self.filter_group = QButtonGroup(self)
        self.filter_buttons = []
        for mode in range(4):
            control = QPushButton()
            control.setObjectName("filter")
            control.setCheckable(True)
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            self.filter_group.addButton(control, mode)
            filters.addWidget(control)
            self.filter_buttons.append(control)
        self.filter_buttons[0].setChecked(True)
        self.filter_group.idClicked.connect(self.set_filter)
        filters.addStretch()
        filters.addWidget(label("Suche", "caption"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Bilddatei suchen")
        self.search.setAccessibleName("Bilder nach Dateiname suchen")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(self.set_search)
        filters.addWidget(self.search)
        workspace_layout.addLayout(filters)

        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.setChildrenCollapsible(False)
        horizontal.setHandleWidth(10)
        results_panel, results_layout = panel()
        results_panel.setMinimumWidth(360)
        results_layout.setContentsMargins(0, 12, 0, 0)
        list_title = QHBoxLayout()
        list_title.setContentsMargins(16, 0, 16, 0)
        list_title.addWidget(label("Ihre Bilder", "section"))
        list_title.addStretch()
        self.list_count = label("", "caption")
        list_title.addWidget(self.list_count)
        results_layout.addLayout(list_title)
        self.table = QTableView()
        self.table.setAccessibleName("Bildliste und Ergebnisse")
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
        self.table.setItemDelegateForColumn(2, StatusDelegate(self.table))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 72)
        self.table.setColumnWidth(2, 136)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed)
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.table)
        self.no_matches = label("Keine Bilder für diese Auswahl.\nÄndern Sie die Suche oder den Filter.", "muted", True)
        self.no_matches.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_stack.addWidget(self.no_matches)
        results_layout.addWidget(self.list_stack)
        horizontal.addWidget(results_panel)

        preview_panel, preview_layout = panel()
        preview_panel.setMinimumWidth(400)
        preview_header = QHBoxLayout()
        self.file_label = label("Wählen Sie links ein Bild aus.", "section")
        self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        preview_header.addWidget(self.file_label, 1)
        self.previous_button = button("‹", lambda: self.move_selection(-1))
        self.previous_button.setAccessibleName("Vorheriges Bild")
        self.previous_button.setToolTip("Vorheriges Bild · Pfeil nach links")
        self.next_button = button("›", lambda: self.move_selection(1))
        self.next_button.setAccessibleName("Nächstes Bild")
        self.next_button.setToolTip("Nächstes Bild · Pfeil nach rechts")
        preview_header.addWidget(self.previous_button)
        preview_header.addWidget(self.next_button)
        preview_layout.addLayout(preview_header)
        self.views = QTabWidget()
        self.views.setAccessibleName("Originalbild oder Schneehöhen anzeigen")
        image_page = QWidget()
        image_layout = QVBoxLayout(image_page)
        image_layout.setContentsMargins(0, 8, 0, 0)
        image_layout.setSpacing(4)
        self.preview_stack = QStackedWidget()
        self.preview = ImagePreview()
        self.preview_stack.addWidget(self.preview)
        self.no_preview = label("Wählen Sie ein Bild aus der Liste.", "noPreview", True)
        self.no_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_stack.addWidget(self.no_preview)
        self.preview_stack.setMinimumHeight(96)
        image_layout.addWidget(self.preview_stack, 1)
        view_controls = QHBoxLayout()
        self.position_label = label("", "caption")
        view_controls.addWidget(self.position_label, 1)
        zoom_out = button("−", lambda: self.preview.zoom(1 / 1.2), "quiet")
        zoom_out.setAccessibleName("Bild verkleinern")
        zoom_in = button("+", lambda: self.preview.zoom(1.2), "quiet")
        zoom_in.setAccessibleName("Bild vergrößern")
        view_controls.addWidget(zoom_out)
        view_controls.addWidget(zoom_in)
        view_controls.addWidget(button("Einpassen", self.preview.fit, "quiet"))
        image_layout.addLayout(view_controls)
        self.views.addTab(image_page, "Originalbild")
        preview_layout.addWidget(self.views, 1)
        result_header = QHBoxLayout()
        self.result_label = label("—", "height")
        self.badge = label("", "badge")
        result_header.addWidget(self.result_label)
        result_header.addWidget(self.badge)
        result_header.addStretch()
        self.recheck_button = button("Erneut auswerten", self.recheck_selected, "quiet")
        result_header.addWidget(self.recheck_button)
        preview_layout.addLayout(result_header)
        self.reason_label = label("", "muted", True)
        preview_layout.addWidget(self.reason_label)
        horizontal.addWidget(preview_panel)
        horizontal.setSizes([430, 850])
        horizontal.setMinimumHeight(320)
        chart_page = QWidget()
        chart_layout = QVBoxLayout(chart_page)
        chart_layout.setContentsMargins(4, 12, 4, 4)
        chart_head = QHBoxLayout()
        chart_head.addWidget(label("Automatische Messwerte", "section"))
        self.maximum_label = label("", "caption")
        chart_head.addWidget(self.maximum_label)
        chart_head.addStretch()
        chart_layout.addLayout(chart_head)
        self.chart = HeightChart(self.library.rows)
        self.chart.selected.connect(self.select_chart_row)
        chart_layout.addWidget(self.chart, 1)
        chart_layout.addWidget(label("Importreihenfolge, keine Zeitachse. Ein Klick auf einen Messpunkt öffnet das Originalbild.", "caption", True))
        self.views.addTab(chart_page, "Schneehöhen")
        workspace_layout.addWidget(horizontal, 1)
        self.body.addWidget(workspace)
        layout.addWidget(self.body, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        self.message = label("Bereit für Ihre Stationsbilder.", "caption")
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.message, 1)
        footer.addWidget(label("Bilder und Ergebnisse bleiben lokal", "caption"))
        layout.addLayout(footer)
        for key, action in [("Ctrl+O", self.choose_files), ("Ctrl+Shift+O", self.choose_folder), ("Ctrl+E", self.export), ("Ctrl+F", self.search.setFocus)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)
        for key, delta in [("Left", -1), ("Right", 1)]:
            shortcut = QShortcut(QKeySequence(key), self.preview)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda d=delta: self.move_selection(d))
        self.refresh()
        if self.library.rows:
            self.table.selectRow(0)
            self.message.setText(f"{len(self.library.rows)} Bilder aus Ihrer letzten Auswertung geöffnet.")

    def selected_index(self):
        selected = self.table.selectionModel().selectedRows()
        return self.proxy.mapToSource(selected[0]).row() if selected else None

    def refresh(self):
        rows = self.library.rows
        counts = {"measured": 0, "review": 0, "pending": 0}
        heights = []
        for row in rows:
            result = row["result"]
            if not result:
                counts["pending"] += 1
            elif result["status"] == "measured":
                counts["measured"] += 1
                heights.append(result["snow_height_cm"])
            else:
                counts["review"] += 1
        for control, title, count in zip(self.filter_buttons, ["Alle", "Gemessen", "Prüfen", "Offen"], [len(rows), counts["measured"], counts["review"], counts["pending"]]):
            control.setText(f"{title}  {count}")
        self.maximum_label.setText(f"  Höchster Messwert: {max(heights):g} cm".replace(".", ",") if heights else "")
        self.body.setCurrentIndex(1 if rows else 0)
        self.toolbar.setVisible(bool(rows))
        busy = self.worker is not None
        self.add_button.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        self.start_button.setVisible(not busy and counts["pending"] > 0)
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy and not self.stopping)
        self.export_button.setEnabled(bool(counts["measured"] + counts["review"]))
        self.remove_action.setEnabled(not busy and self.selected_index() is not None)
        self.clear_action.setEnabled(bool(rows) and not busy)
        self.recheck_button.setEnabled(not busy and self.selected_index() is not None)
        self.list_count.setText(f"{self.proxy.rowCount()} von {len(rows)}")
        self.list_stack.setCurrentIndex(0 if self.proxy.rowCount() else 1)
        self.chart.update()

    def choose_files(self):
        if self.worker:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Stationsbilder auswählen", "", "Stationsbilder (*.jpg *.jpeg *.png)")
        if files:
            self.add_paths([Path(path) for path in files])

    def choose_folder(self):
        if self.worker:
            return
        folder = QFileDialog.getExistingDirectory(self, "Bildordner auswählen")
        if folder:
            self.add_paths(sorted(path for path in Path(folder).rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}))

    def add_paths(self, paths):
        if self.worker:
            return
        previous_count = len(self.library.rows)
        self.model.beginResetModel()
        try:
            count = self.library.add(paths)
        except (OSError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Bilder nicht hinzugefügt", str(exc))
            count = 0
        finally:
            self.model.endResetModel()
        self.refresh()
        if count:
            self.select_source_row(previous_count)
            self.start_analysis()
        else:
            self.message.setText("Diese Bilder sind bereits in der Liste." if paths else "In diesem Ordner wurden keine JPG- oder PNG-Bilder gefunden.")

    def set_filter(self, mode):
        current = self.selected_index()
        self.proxy.beginFilterChange()
        self.proxy.mode = mode
        self.filter_buttons[mode].setChecked(True)
        self.proxy.endFilterChange(self.proxy.Direction.Rows)
        self.keep_selection(current)
        self.refresh()

    def set_search(self, text):
        current = self.selected_index()
        self.proxy.beginFilterChange()
        self.proxy.search = text.strip().casefold()
        self.proxy.endFilterChange(self.proxy.Direction.Rows)
        self.keep_selection(current)
        self.refresh()

    def keep_selection(self, source_index):
        mapped = self.proxy.mapFromSource(self.model.index(source_index, 0)) if source_index is not None else None
        if mapped is not None and mapped.isValid():
            self.table.selectRow(mapped.row())
        elif self.proxy.rowCount():
            self.table.selectRow(0)
        else:
            self.table.clearSelection()
        self.selection_changed()

    def select_source_row(self, index):
        mapped = self.proxy.mapFromSource(self.model.index(index, 0))
        if not mapped.isValid():
            self.search.clear()
            self.set_filter(0)
            mapped = self.proxy.mapFromSource(self.model.index(index, 0))
        self.table.selectRow(mapped.row())
        self.table.scrollTo(mapped)
        self.selection_changed()

    def move_selection(self, delta):
        selected = self.table.selectionModel().selectedRows()
        if selected:
            row = selected[0].row() + delta
            if 0 <= row < self.proxy.rowCount():
                self.table.selectRow(row)
                self.table.scrollTo(self.proxy.index(row, 0))

    def select_chart_row(self, index):
        self.select_source_row(index)
        self.views.setCurrentIndex(0)

    def selection_changed(self, *_):
        index = self.selected_index()
        self.chart.selected_row = index if index is not None else -1
        self.chart.update()
        self.remove_action.setEnabled(index is not None and not self.worker)
        self.recheck_button.setEnabled(index is not None and not self.worker)
        selected = self.table.selectionModel().selectedRows()
        position = selected[0].row() if selected else -1
        self.previous_button.setEnabled(position > 0)
        self.next_button.setEnabled(0 <= position < self.proxy.rowCount() - 1)
        if index is None:
            self.preview.show_file(None)
            self.file_label.setText("Wählen Sie links ein Bild aus.")
            self.preview_stack.setCurrentIndex(1)
            self.no_preview.setText("Wählen Sie ein Bild aus der Liste.")
            self.result_label.setText("—")
            self.badge.hide()
            self.reason_label.setText("")
            self.position_label.setText("")
            return
        row = self.library.rows[index]
        result = row["result"]
        status = result["status"] if result else "pending"
        available = self.preview.show_file(row["path"])
        self.preview_stack.setCurrentIndex(0 if available else 1)
        self.no_preview.setText("Dieses Originalbild ist nicht verfügbar.\nPrüfen Sie den Speicherort und das Bildformat.")
        self.file_label.setText(Path(row["path"]).name)
        self.file_label.setToolTip(row["path"])
        self.position_label.setText(f"Bild {index + 1} von {len(self.library.rows)}  ·  Mausrad zum Zoomen")
        self.result_label.setText(height_text(result) + " cm" if status == "measured" else "—")
        self.badge.setText("Wird ausgewertet" if index == self.current_row else STATUS[status])
        self.badge.setStyleSheet(f"color: {COLORS[status]}; background: {BACKGROUNDS[status]};")
        self.badge.show()
        self.reason_label.setText(explanation(result))

    def start_analysis(self, indices=None):
        if self.worker:
            return
        if not isinstance(indices, list):
            indices = [i for i, row in enumerate(self.library.rows) if row["result"] is None]
        jobs = [(i, self.library.rows[i]["path"]) for i in indices]
        if not jobs:
            return
        self.finished_count = 0
        self.jobs_total = len(jobs)
        self.run_error = False
        self.stopping = False
        self.progress.setRange(0, 0)
        self.progress.show()
        self.message.setText("Bildauswertung wird vorbereitet. Die Modelle werden auf diesem Computer geladen …")
        self.worker = AnalysisWorker(jobs, self)
        self.worker.current.connect(self.on_current)
        self.worker.result.connect(self.on_result)
        self.worker.failed.connect(self.on_failure)
        self.worker.finished.connect(self.on_finished)
        self.refresh()
        self.worker.start()

    def on_current(self, index, name):
        previous = self.current_row
        self.current_row = index
        self.model.active_row = index
        for row in {previous, index} - {-1}:
            self.model.dataChanged.emit(self.model.index(row, 0), self.model.index(row, 2))
        self.progress.setRange(0, self.jobs_total)
        self.progress.setValue(self.finished_count)
        if not self.stopping:
            self.message.setText(f"Bild {self.finished_count + 1} von {self.jobs_total} wird ausgewertet · {name}")
        self.selection_changed()

    def on_result(self, index, result):
        try:
            self.library.save_result(index, result)
        except sqlite3.Error as exc:
            self.run_error = True
            self.worker.requestInterruption()
            QMessageBox.critical(self, "Ergebnis konnte nicht gespeichert werden", str(exc))
            return
        self.model.active_row = -1
        self.current_row = -1
        self.model.dataChanged.emit(self.model.index(index, 0), self.model.index(index, 2))
        self.finished_count += 1
        self.progress.setValue(self.finished_count)
        self.refresh()
        self.selection_changed()

    def on_failure(self, message):
        self.run_error = True
        QMessageBox.critical(self, "Analyse nicht verfügbar", message)

    def stop_analysis(self):
        if self.worker:
            self.stopping = True
            self.worker.requestInterruption()
            self.message.setText("Wird nach dem laufenden Bild angehalten. Ergebnisse bleiben gespeichert.")
            self.refresh()

    def on_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.current_row = -1
        self.model.active_row = -1
        self.progress.hide()
        if self.run_error:
            text = f"Auswertung mit Fehler beendet. {self.finished_count} Ergebnisse gespeichert."
        elif self.stopping:
            text = f"Angehalten · {self.finished_count} Bilder ausgewertet. Mit „Auswertung fortsetzen“ geht es weiter."
        else:
            text = f"Auswertung abgeschlossen · {self.finished_count} Bilder ausgewertet und gespeichert."
        self.message.setText(text)
        self.refresh()
        self.selection_changed()
        if self.closing:
            self.close()

    def recheck_selected(self):
        index = self.selected_index()
        if index is None or self.worker:
            return
        try:
            self.library.reset_result(index)
        except sqlite3.Error as exc:
            QMessageBox.warning(self, "Bild konnte nicht vorbereitet werden", str(exc))
            return
        self.preview.show_file(None)
        self.model.dataChanged.emit(self.model.index(index, 0), self.model.index(index, 2))
        self.select_source_row(index)
        self.start_analysis([index])

    def export(self):
        if not any(row["result"] for row in self.library.rows):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Ergebnisse für Excel speichern", "Schneepegel_Brotenau.csv", "CSV-Tabelle (*.csv)")
        if path:
            try:
                export_csv(Path(path), self.library.rows)
            except OSError as exc:
                QMessageBox.warning(self, "Export nicht möglich", str(exc))
            else:
                self.message.setText(f"Tabelle gespeichert · {Path(path).name}")

    def confirm(self, title, text, action):
        question = QMessageBox(QMessageBox.Icon.Question, title, text, parent=self)
        accept = question.addButton(action, QMessageBox.ButtonRole.AcceptRole)
        cancel = question.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        question.setDefaultButton(cancel)
        question.exec()
        return question.clickedButton() == accept

    def remove_selected(self):
        index = self.selected_index()
        if index is None or self.worker:
            return
        if not self.confirm("Bild aus der Liste entfernen?", "Das Bild und sein Ergebnis aus dieser Liste entfernen? Die Originaldatei bleibt erhalten.", "Aus Liste entfernen"):
            return
        self.model.beginResetModel()
        try:
            self.library.remove(index)
        except sqlite3.Error as exc:
            QMessageBox.warning(self, "Bild konnte nicht entfernt werden", str(exc))
        finally:
            self.model.endResetModel()
        self.keep_selection(min(index, len(self.library.rows) - 1) if self.library.rows else None)
        self.refresh()

    def clear(self):
        if self.worker or not self.library.rows:
            return
        if not self.confirm("Bildliste leeren?", "Alle Bilder und gespeicherten Ergebnisse aus dieser Liste entfernen? Die Originaldateien bleiben erhalten.", "Liste leeren"):
            return
        self.model.beginResetModel()
        try:
            self.library.clear()
        except sqlite3.Error as exc:
            QMessageBox.warning(self, "Liste konnte nicht geleert werden", str(exc))
        finally:
            self.model.endResetModel()
        self.selection_changed()
        self.refresh()

    def help(self):
        QMessageBox.information(self, "Schneepegel Brotenau", "Bilder auswählen oder einen Ordner in das Fenster ziehen. Die Auswertung beginnt automatisch.\n\nMit „Prüfen“ sehen Sie alle Aufnahmen ohne freigegebenen Messwert. Klicken Sie auf eine Zeile oder einen Punkt im Diagramm, um das Originalbild groß anzusehen. Mausrad: zoomen. Ziehen: Bild verschieben.\n\n„Erneut auswerten“ verarbeitet nur das ausgewählte Bild. „Für Excel exportieren“ speichert die gesamte Bildliste. Fehlende Messwerte bleiben leer, gemessene Nullwerte stehen als 0 in der Tabelle.\n\nDie Bilder werden nicht kopiert oder verändert. Bildliste und Ergebnisse werden automatisch lokal gespeichert.\n\nNur für die kalibrierte Kamera in Brotenau, JPG/PNG mit 1920 × 1080 Pixeln. Ausgabebereich 0–80 cm in 1-cm-Schritten; die Schrittweite ist keine Genauigkeitsgarantie. Reale Trainingsbilder über 25 cm fehlen bislang. Die Grafik zeigt die Importreihenfolge, keine Zeitachse. Eingebrannte Zeitstempel werden nicht automatisch ausgelesen.\n\nAnhalten und Schließen warten auf die laufende Berechnung. Kein Analyse-Zeitlimit, keine automatischen Wiederholungen, keine feste Bildanzahlgrenze. Ein Bild gleichzeitig; PyTorch und numerische Bibliotheken: je 2 CPU-Threads, OpenCV: 1, PyTorch Interop: 1, Regressoren: je 1 Worker. SQLite: bis zu 5 Sekunden Wartezeit bei Dateisperren.\n\nTastenkürzel: Strg+O Bilder, Strg+Umschalt+O Ordner, Strg+F Suche, Strg+E Export.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.worker:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
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
            self.message.setText("Die App schließt nach der laufenden Berechnung und speichert das Ergebnis.")
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
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "app.ico")))
    storage = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "ergebnisse.sqlite3"
    try:
        window = MainWindow(storage)
    except (OSError, sqlite3.Error) as exc:
        QMessageBox.critical(None, "Schneepegel konnte nicht geöffnet werden", f"Die gespeicherten Ergebnisse konnten nicht geöffnet werden.\n\n{exc}")
        return 1
    window.show()
    return app.exec()
