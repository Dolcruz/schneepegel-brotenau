import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEventLoop, Qt

from desktop.worker import AnalysisWorker
from height_model.predict_pipeline import SnowAnalyzer


class Regressor:
    n_jobs = -1


class FakeAnalyzer:
    def __init__(self, _):
        self.models = {"positive_height_regressor": Regressor()}
        self.direct_regressor = Regressor()
        self.low_range_regressor = Regressor()

    def predict(self, image):
        if image.name == "broken.jpg":
            raise OSError("Bild kann nicht gelesen werden")
        if image.suffix == ".png":
            # The real input checks run before any model is used.
            return SnowAnalyzer.predict(self, image)
        return {"status": "measured", "snow_height_cm": 0, "reason": "clear_zero_context"}


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def run_worker(self, paths, stop_after_first=False):
        worker = AnalysisWorker(list(enumerate(paths)))
        results = []
        worker.result.connect(lambda i, r: results.append((i, r)), Qt.ConnectionType.DirectConnection)
        if stop_after_first:
            worker.current.connect(lambda *_: worker.requestInterruption(), Qt.ConnectionType.DirectConnection)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        with patch("height_model.predict_pipeline.SnowAnalyzer", FakeAnalyzer):
            worker.start()
            loop.exec()
            worker.wait()
        return results

    def test_corrupt_file_does_not_stop_remaining_images(self):
        results = self.run_worker(["broken.jpg", "valid.jpg"])
        self.assertEqual([r[1]["status"] for r in results], ["error", "measured"])
        self.assertIsNone(results[0][1]["snow_height_cm"])

    def test_stop_finishes_current_image_and_leaves_rest_pending(self):
        results = self.run_worker(["first.jpg", "second.jpg"], stop_after_first=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 0)
        self.assertEqual(results[0][1]["status"], "measured")

    def test_wrong_resolution_is_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "wrong.png"
            Image.new("RGB", (320, 240)).save(image)
            analyzer = SnowAnalyzer.__new__(SnowAnalyzer)
            with self.assertRaisesRegex(ValueError, "1920"):
                analyzer.predict(image)

    def test_oversized_image_does_not_stop_remaining_images(self):
        # Pillow refuses images above about 179 megapixels while opening them.
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        header = struct.pack(">IIBBBBB", 20000, 10000, 8, 2, 0, 0, 0)
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "panorama.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b""))
            results = self.run_worker([str(image), "valid.jpg"])
        self.assertEqual([r[1]["status"] for r in results], ["error", "measured"])
        self.assertIn("1920", results[0][1]["reason"])


if __name__ == "__main__":
    unittest.main()
