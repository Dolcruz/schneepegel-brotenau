from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


REFERENCE_ANCHOR = (950, 315)
TEMPLATE_SIZE = (55, 90)
SEARCH_X = (930, 1025)
SEARCH_MARGIN_Y = 20
MIN_ANCHOR_SCORE = 0.20
REFERENCE_BUNDLE = Path(__file__).resolve().parent / "resources" / "reference_bundle.npz"


def _gradient(image: np.ndarray) -> np.ndarray:
    equalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(image)
    grad_x = cv2.Sobel(equalized, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(equalized, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(grad_x, grad_y)


def load_anchor_template() -> np.ndarray:
    with np.load(REFERENCE_BUNDLE) as bundle:
        return bundle["fallback_anchor_template"].copy()


def locate_anchor(image: np.ndarray, template: np.ndarray) -> tuple[int, int, float]:
    expected_x, expected_y = REFERENCE_ANCHOR
    _, template_height = TEMPLATE_SIZE
    y0 = expected_y - SEARCH_MARGIN_Y
    y1 = expected_y + template_height + SEARCH_MARGIN_Y
    region = image[y0:y1, SEARCH_X[0] : SEARCH_X[1]]
    response = cv2.matchTemplate(_gradient(region), template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(response)
    x = SEARCH_X[0] + location[0]
    y = y0 + location[1]
    if score < MIN_ANCHOR_SCORE:
        x, y = expected_x, expected_y
    return x, y, float(score)


def extract_peg_profile(image_path: Path, template: np.ndarray) -> tuple[np.ndarray, float]:
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or image.shape != (1080, 1920):
        raise RuntimeError(f"Unerwartetes Bildformat: {image_path}")
    x, y, score = locate_anchor(image, template)
    peg = image[y : y + 500, x + 5 : x + 50]
    if peg.shape != (500, 45):
        raise RuntimeError(f"Pegelbereich liegt außerhalb des Bildes: {image_path}")
    grad_x = np.abs(cv2.Sobel(peg, cv2.CV_32F, 1, 0, ksize=3))
    grad_y = np.abs(cv2.Sobel(peg, cv2.CV_32F, 0, 1, ksize=3))
    profile = np.column_stack(
        [
            *((peg < threshold).mean(axis=1) for threshold in [60, 90, 120, 150, 180]),
            peg.mean(axis=1) / 255.0,
            peg.std(axis=1) / 128.0,
            grad_x.mean(axis=1) / 255.0,
            grad_y.mean(axis=1) / 255.0,
        ]
    )
    return profile.astype(np.float32).ravel(), score


def extract_context_features(image_path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[:2] != (1080, 1920):
        raise RuntimeError(f"Unerwartetes Bildformat: {image_path}")
    image = cv2.resize(image[:1035], (320, 180), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    features: list[float] = []
    for grid_y in range(3):
        for grid_x in range(4):
            y0, y1 = grid_y * 60, (grid_y + 1) * 60
            x0, x1 = grid_x * 80, (grid_x + 1) * 80
            bgr_region = image[y0:y1, x0:x1]
            hsv_region = hsv[y0:y1, x0:x1]
            features.extend(bgr_region.mean(axis=(0, 1)) / 255.0)
            features.extend(bgr_region.std(axis=(0, 1)) / 128.0)
            features.extend(hsv_region.mean(axis=(0, 1)) / np.array([180.0, 255.0, 255.0]))
            for saturation in [35, 60, 90]:
                for brightness in [130, 170, 210]:
                    features.append(
                        float(
                            np.mean(
                                (hsv_region[:, :, 1] < saturation)
                                & (hsv_region[:, :, 2] > brightness)
                            )
                        )
                    )
            features.append(
                float(
                    np.mean(
                        (hsv_region[:, :, 0] >= 25)
                        & (hsv_region[:, :, 0] <= 95)
                        & (hsv_region[:, :, 1] > 35)
                        & (hsv_region[:, :, 2] > 35)
                    )
                )
            )
            features.append(float(np.mean(hsv_region[:, :, 2] < 70)))
    for array, divisors in [
        (image, np.array([255.0, 255.0, 255.0])),
        (hsv, np.array([180.0, 255.0, 255.0])),
        (lab, np.array([255.0, 255.0, 255.0])),
    ]:
        for channel in range(3):
            features.extend(
                np.percentile(array[:, :, channel], [5, 25, 50, 75, 95])
                / divisors[channel]
            )
    return np.asarray(features, dtype=np.float32)
