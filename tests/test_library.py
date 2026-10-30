import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from desktop.library import Library, export_csv


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = Library(self.root / "results.sqlite3")

    def tearDown(self):
        self.library.close()
        self.temp.cleanup()

    def test_persistence_duplicates_and_missing_original(self):
        path = self.root / "Schneehöhe ÄÖÜ.jpg"
        path.write_bytes(b"original bytes")
        self.assertEqual(self.library.add([path, path]), 1)
        self.library.save_result(0, {"status": "measured", "snow_height_cm": 0, "reason": "clear_zero_context"})
        path.unlink()
        reopened = Library(self.root / "results.sqlite3")
        self.assertEqual(reopened.rows, self.library.rows)
        self.assertEqual(reopened.add([path]), 0)
        reopened.close()

    def test_csv_preserves_zero_and_missing_values_and_escapes_formula(self):
        self.library.add([self.root / name for name in ("zero.jpg", "uncertain.jpg", "unusable.jpg", "=1+1.jpg", "pending.jpg")])
        for i, status in enumerate(["measured", "uncertain", "unusable", "error"]):
            self.library.save_result(i, {"status": status, "snow_height_cm": 0 if i == 0 else None, "reason": "quality_filter"})
        target = self.root / "export.csv"
        export_csv(target, self.library.rows)
        with target.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=";"))
        self.assertEqual(rows[1][3], "0")
        self.assertEqual([r[3] for r in rows[2:]], ["", "", "", ""])
        self.assertTrue(rows[4][0].startswith("'="))

    def test_clearing_keeps_originals(self):
        source = self.root / "original.png"
        source.write_bytes(b"unchanged")
        self.library.add([source])
        self.library.clear()
        self.assertEqual(source.read_bytes(), b"unchanged")
        reopened = Library(self.root / "results.sqlite3")
        self.assertEqual(reopened.rows, [])
        reopened.close()

    def test_failed_database_write_does_not_change_visible_library(self):
        self.library.connection.execute("PRAGMA query_only=ON")
        with self.assertRaises(sqlite3.OperationalError):
            self.library.add([self.root / "new.png"])
        self.assertEqual(self.library.rows, [])

    def test_recheck_and_remove_change_only_selected_record(self):
        paths = [self.root / name for name in ("first.png", "second.png")]
        for path in paths:
            path.write_bytes(b"original")
        self.library.add(paths)
        result = {"status": "measured", "snow_height_cm": 3, "reason": "positive_peg_model"}
        self.library.save_result(0, result)
        self.library.save_result(1, result)
        self.library.reset_result(1)
        self.assertEqual(self.library.rows[0]["result"], result)
        self.assertIsNone(self.library.rows[1]["result"])
        self.library.remove(1)
        reopened = Library(self.root / "results.sqlite3")
        self.assertEqual(len(reopened.rows), 1)
        self.assertEqual(reopened.rows[0]["result"], result)
        reopened.close()
        self.assertTrue(all(path.read_bytes() == b"original" for path in paths))


if __name__ == "__main__":
    unittest.main()
