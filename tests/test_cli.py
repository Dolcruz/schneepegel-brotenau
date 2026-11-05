import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from height_model import predict_pipeline


class FakeAnalyzer:
    def predict(self, image):
        if image.name == "broken.jpg":
            raise OSError("Bild kann nicht gelesen werden")
        return {"image": str(image), "status": "measured", "snow_height_cm": 0.0, "reason": "clear_zero_context"}


class CommandLineTests(unittest.TestCase):
    def test_unreadable_image_is_reported_and_remaining_images_are_evaluated(self):
        output = io.StringIO()
        with patch.object(predict_pipeline, "SnowAnalyzer", FakeAnalyzer), \
                patch("sys.argv", ["predict_pipeline", "broken.jpg", "valid.jpg"]), \
                redirect_stdout(output):
            code = predict_pipeline.main()
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([line["status"] for line in lines], ["error", "measured"])
        self.assertIsNone(lines[0]["snow_height_cm"])
        self.assertEqual(lines[0]["reason"], "Bild kann nicht gelesen werden")
        self.assertEqual(lines[1]["snow_height_cm"], 0.0)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
