import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from height_model.features import extract_context_features, extract_peg_profile, load_anchor_template
from height_model.geometric_meter import extract_runtime_scores


class OrientationTests(unittest.TestCase):
    """The calibration refers to the stored camera pixels, as do Pillow and the preview."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        pixels = np.random.default_rng(7).integers(0, 256, (1080, 1920, 3), dtype=np.uint8)
        image = Image.fromarray(pixels)
        cls.plain = root / "plain.jpg"
        image.save(cls.plain, quality=92)
        cls.tagged = {}
        for orientation in (3, 6):
            exif = Image.Exif()
            exif[0x0112] = orientation
            path = root / f"orientation-{orientation}.jpg"
            image.save(path, quality=92, exif=exif.tobytes())
            cls.tagged[orientation] = path
        cls.template = load_anchor_template()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_exif_orientation_does_not_change_analysed_pixels(self):
        context = extract_context_features(self.plain)
        profile, score = extract_peg_profile(self.plain, self.template)
        scores = extract_runtime_scores(self.plain)
        for orientation, path in self.tagged.items():
            with self.subTest(orientation=orientation):
                with Image.open(path) as source:
                    self.assertEqual(source.size, (1920, 1080))
                np.testing.assert_array_equal(extract_context_features(path), context)
                tagged_profile, tagged_score = extract_peg_profile(path, self.template)
                np.testing.assert_array_equal(tagged_profile, profile)
                self.assertEqual(tagged_score, score)
                tagged_scores = extract_runtime_scores(path)
                self.assertEqual(tagged_scores["available"], scores["available"])
                if scores["available"]:
                    np.testing.assert_array_equal(tagged_scores["scores"], scores["scores"])


if __name__ == "__main__":
    unittest.main()
