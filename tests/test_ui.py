import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from desktop.app import MainWindow, STYLE


class FakeWorker(QObject):
    current = Signal(int, str)
    result = Signal(int, dict)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, jobs, parent):
        super().__init__(parent)
        self.jobs = jobs
        self.interrupted = False
        self.started = False

    def start(self):
        self.started = True

    def requestInterruption(self):
        self.interrupted = True


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.worker_patch = patch("desktop.app.AnalysisWorker", FakeWorker)
        self.worker_patch.start()
        self.window = MainWindow(self.root / "library.sqlite3")
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window.worker:
            self.window.worker.finished.emit()
        self.window.close()
        self.worker_patch.stop()
        self.app.processEvents()
        self.directory.cleanup()

    def images(self):
        paths = [self.root / name for name in ["winter-01.png", "winter-02.png"]]
        for path in paths:
            Image.new("RGB", (1920, 1080), "white").save(path)
        return paths

    def complete(self):
        worker = self.window.worker
        worker.result.emit(0, {"status": "measured", "snow_height_cm": 5, "reason": "positive_peg_model"})
        worker.result.emit(1, {"status": "uncertain", "snow_height_cm": None, "reason": "height_disagreement"})
        worker.finished.emit()
        self.app.processEvents()

    def test_import_starts_once_and_duplicates_do_not_restart(self):
        paths = self.images()
        self.window.add_paths(paths)
        worker = self.window.worker
        self.assertTrue(worker.started)
        self.assertEqual(len(worker.jobs), 2)
        self.complete()
        self.window.add_paths(paths)
        self.assertIsNone(self.window.worker)
        self.assertEqual(len(self.window.library.rows), 2)

    def test_pause_then_resume_only_remaining_images(self):
        self.window.add_paths(self.images())
        worker = self.window.worker
        worker.result.emit(0, {"status": "measured", "snow_height_cm": 0, "reason": "clear_zero_context"})
        self.window.stop_analysis()
        self.assertTrue(worker.interrupted)
        worker.finished.emit()
        self.assertIsNone(self.window.worker)
        self.assertIsNone(self.window.library.rows[1]["result"])
        self.window.start_analysis()
        self.assertEqual([index for index, _ in self.window.worker.jobs], [1])

    def test_search_filter_and_chart_navigation_share_selection(self):
        self.window.add_paths(self.images())
        self.complete()
        self.window.set_filter(2)
        self.assertEqual(self.window.proxy.rowCount(), 1)
        self.assertEqual(self.window.selected_index(), 1)
        self.window.search.setText("not-found")
        self.assertEqual(self.window.proxy.rowCount(), 0)
        self.assertIsNone(self.window.selected_index())
        self.window.views.setCurrentIndex(1)
        self.window.select_chart_row(0)
        self.assertEqual(self.window.selected_index(), 0)
        self.assertEqual(self.window.views.currentIndex(), 0)
        self.assertEqual(self.window.search.text(), "")

    def test_results_do_not_reset_image_zoom(self):
        self.window.add_paths(self.images())
        self.window.select_source_row(0)
        self.window.preview.zoom(2)
        transform = self.window.preview.transform()
        self.window.worker.result.emit(0, {"status": "measured", "snow_height_cm": 5, "reason": "positive_peg_model"})
        self.app.processEvents()
        self.assertEqual(self.window.preview.transform(), transform)

    def test_recheck_processes_only_selected_image(self):
        self.window.add_paths(self.images())
        self.complete()
        self.window.set_filter(2)
        self.window.recheck_selected()
        self.assertEqual([index for index, _ in self.window.worker.jobs], [1])
        self.assertEqual(self.window.library.rows[0]["result"]["snow_height_cm"], 5)
        self.assertEqual(self.window.selected_index(), 1)

    def test_compact_window_keeps_preview_and_result_inside_panel(self):
        self.window.add_paths(self.images())
        self.complete()
        self.window.resize(1000, 700)
        self.app.processEvents()
        parent = self.window.reason_label.parentWidget()
        self.assertGreaterEqual(self.window.preview.height(), 96)
        self.assertLessEqual(self.window.reason_label.geometry().bottom(), parent.height())
        self.assertGreater(self.window.result_label.geometry().top(), self.window.views.geometry().bottom())

    def test_removing_and_readding_file_shows_current_pixels(self):
        paths = self.images()
        self.window.add_paths(paths)
        self.complete()
        with patch.object(self.window, "confirm", return_value=True):
            self.window.select_source_row(0)
            self.window.remove_selected()
            self.window.remove_selected()
        Image.new("RGB", (1920, 1080), "black").save(paths[1])
        self.window.add_paths([paths[1]])
        pixel = self.window.preview.item.pixmap().toImage().pixelColor(0, 0)
        self.assertEqual((pixel.red(), pixel.green(), pixel.blue()), (0, 0, 0))
