from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
REFERENCE_BUNDLE_PATH = RESOURCE_DIR / "reference_bundle.npz"
CALIBRATION_PATH = RESOURCE_DIR / "peg_calibration.json"
REFERENCE_NAME = "TLC00136_frame_4.jpg"
HEIGHT_GRID_CM = np.arange(2.0, 85.0, 2.0)
ROI = (935, 310, 1015, 770)  # left, top, right, bottom in reference coordinates
HALF_PATCH_WIDTH_PX = 18
HALF_WINDOW_CM = 2.0
MAX_REPORTED_HEIGHT_CM = 80.0
ANCHOR_SPECS = {
    "tip": (957, 320, 38, 26),
    "top": (950, 315, 55, 90),
    "mid": (950, 415, 55, 90),
}
SEARCH_X = (930, 1025)
SEARCH_MARGIN_Y = 20
TWO_ANCHOR_MIN_SCORE = 0.42
SINGLE_ANCHOR_MIN_SCORE = 0.30


@dataclass(frozen=True)
class PegCalibration:
    heights_cm: np.ndarray
    x_px: np.ndarray
    y_px: np.ndarray

    def point(self, height_cm: float) -> tuple[float, float]:
        return (
            _linear_interpolate_with_extrapolation(height_cm, self.heights_cm, self.x_px),
            _linear_interpolate_with_extrapolation(height_cm, self.heights_cm, self.y_px),
        )


def load_calibration(path: Path = CALIBRATION_PATH) -> PegCalibration:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("finalized"):
        raise RuntimeError("Die Pegelkalibrierung ist noch nicht abgeschlossen.")
    if payload.get("image_filename") != REFERENCE_NAME:
        raise RuntimeError("Die Pegelkalibrierung gehört nicht zum erwarteten Referenzbild.")

    points = payload["points"]
    heights = np.arange(10.0, 81.0, 10.0)
    x_values = np.asarray([points[f"tick_{int(height)}"]["x"] for height in heights])
    y_values = np.asarray([points[f"tick_{int(height)}"]["y"] for height in heights])
    return PegCalibration(heights, x_values, y_values)


def similarity_transform(
    source_top: tuple[float, float],
    source_mid: tuple[float, float],
    destination_top: tuple[float, float],
    destination_mid: tuple[float, float],
) -> np.ndarray:
    source_vector = complex(
        source_mid[0] - source_top[0], source_mid[1] - source_top[1]
    )
    destination_vector = complex(
        destination_mid[0] - destination_top[0],
        destination_mid[1] - destination_top[1],
    )
    if abs(source_vector) < 1:
        raise ValueError("Die beiden Pegelanker liegen zu nah beieinander.")

    factor = destination_vector / source_vector
    matrix = np.asarray(
        [[factor.real, -factor.imag], [factor.imag, factor.real]], dtype=np.float64
    )
    source = np.asarray(source_top, dtype=np.float64)
    destination = np.asarray(destination_top, dtype=np.float64)
    translation = destination - matrix @ source
    return np.column_stack([matrix, translation])


def align_peg_roi(
    gray: np.ndarray,
    transform_to_reference: np.ndarray,
    roi: tuple[int, int, int, int] = ROI,
) -> np.ndarray:
    left, top, right, bottom = roi
    crop_transform = transform_to_reference.copy()
    crop_transform[:, 2] -= np.asarray([left, top])
    return cv2.warpAffine(
        gray,
        crop_transform,
        (right - left, bottom - top),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def visibility_scores(
    aligned_roi: np.ndarray,
    reference_roi: np.ndarray,
    calibration: PegCalibration,
    height_grid_cm: np.ndarray = HEIGHT_GRID_CM,
) -> np.ndarray:
    target_gradient = _gradient(aligned_roi)
    reference_gradient = _gradient(reference_roi)
    left, top, _, _ = ROI
    scores = []
    for height in height_grid_cm:
        x, _ = calibration.point(float(height))
        _, upper_y = calibration.point(float(height + HALF_WINDOW_CM))
        _, lower_y = calibration.point(float(height - HALF_WINDOW_CM))
        x0 = int(round(x - left - HALF_PATCH_WIDTH_PX))
        x1 = int(round(x - left + HALF_PATCH_WIDTH_PX))
        y0 = int(round(min(upper_y, lower_y) - top))
        y1 = int(round(max(upper_y, lower_y) - top))
        target_patch = target_gradient[y0:y1, x0:x1]
        reference_patch = reference_gradient[y0:y1, x0:x1]
        scores.append(_correlation(target_patch, reference_patch))
    return np.asarray(scores, dtype=np.float32)


def visibility_feature_tensor(
    scores: np.ndarray, height_grid_cm: np.ndarray = HEIGHT_GRID_CM
) -> np.ndarray:
    smoothed = scores.copy()
    smoothed[:, 1:-1] = (
        scores[:, :-2] + scores[:, 1:-1] + scores[:, 2:]
    ) / 3.0
    upper_bands = scores[:, height_grid_cm >= 60]
    upper_reference = np.full((len(scores), 1), np.nan, dtype=np.float64)
    valid_rows = np.isfinite(upper_bands).any(axis=1)
    upper_reference[valid_rows, 0] = np.nanmedian(upper_bands[valid_rows], axis=1)
    previous = np.column_stack([scores[:, 0], scores[:, :-1]])
    following = np.column_stack([scores[:, 1:], scores[:, -1]])
    return np.stack(
        [
            scores,
            smoothed,
            scores / np.maximum(upper_reference, 0.05),
            scores - upper_reference,
            following - previous,
        ],
        axis=2,
    )


def direct_regression_features(
    scores: np.ndarray,
    tip_anchor_score: np.ndarray | float,
    top_anchor_score: np.ndarray | float,
    mid_anchor_score: np.ndarray | float,
) -> np.ndarray:
    score_rows = np.atleast_2d(scores)
    profile = visibility_feature_tensor(score_rows).reshape(len(score_rows), -1)
    anchors = np.column_stack(
        [
            np.atleast_1d(tip_anchor_score),
            np.atleast_1d(top_anchor_score),
            np.atleast_1d(mid_anchor_score),
        ]
    )
    if len(anchors) != len(profile):
        raise ValueError("Ankerwerte und Sichtbarkeitsprofile haben verschiedene Längen.")
    return np.column_stack([profile, anchors])


def snowline_from_probabilities(
    visible_probability: np.ndarray,
    height_grid_cm: np.ndarray = HEIGHT_GRID_CM,
    output_offset_cm: float = 1.0,
) -> tuple[float, float]:
    probability = np.clip(visible_probability, 1e-5, 1 - 1e-5)
    boundaries = np.arange(0.0, float(height_grid_cm.max()) + 2.0, 2.0)
    costs = np.asarray(
        [
            -np.log(1 - probability[height_grid_cm <= boundary]).sum()
            - np.log(probability[height_grid_cm > boundary]).sum()
            for boundary in boundaries
        ]
    )
    best = int(np.argmin(costs))
    evidence_gain = float(costs[0] - costs[best])
    reported_height = min(
        float(boundaries[best] + output_offset_cm), MAX_REPORTED_HEIGHT_CM
    )
    return reported_height, evidence_gain


def load_anchor_templates() -> dict[str, np.ndarray]:
    with np.load(REFERENCE_BUNDLE_PATH) as bundle:
        return {
            "tip": bundle["anchor_tip"].copy(),
            "top": bundle["anchor_top"].copy(),
            "mid": bundle["anchor_mid"].copy(),
        }


def locate_anchors(
    gray: np.ndarray, templates: dict[str, np.ndarray]
) -> dict[str, float]:
    result: dict[str, float] = {}
    for name, (_, expected_y, _, height) in ANCHOR_SPECS.items():
        y0 = expected_y - SEARCH_MARGIN_Y
        y1 = expected_y + height + SEARCH_MARGIN_Y
        region = gray[y0:y1, SEARCH_X[0] : SEARCH_X[1]]
        response = cv2.matchTemplate(
            _gradient(region), templates[name], cv2.TM_CCOEFF_NORMED
        )
        _, score, _, location = cv2.minMaxLoc(response)
        x, y = _subpixel_peak(response, location)
        result[f"{name}_x_px"] = SEARCH_X[0] + x
        result[f"{name}_y_px"] = y0 + y
        result[f"{name}_score"] = float(score)
    return result


def measure_geometric_height(
    image_path: Path,
    classifier,
    direct_regressor=None,
    low_range_regressor=None,
) -> dict[str, float | bool]:
    measurement = extract_runtime_scores(image_path)
    if not measurement["available"]:
        return {"available": False}
    scores = measurement.pop("scores")
    features = visibility_feature_tensor(scores[None, :])[0]
    probability = classifier.predict_proba(features)[:, 1]
    height_cm, evidence_gain = snowline_from_probabilities(probability)
    direct_result = {}
    if direct_regressor is not None:
        direct_features = direct_regression_features(
            scores,
            measurement["tip_anchor_score"],
            measurement["top_anchor_score"],
            measurement["mid_anchor_score"],
        )
        direct_height, direct_std = _ensemble_regression_prediction(
            direct_regressor, direct_features
        )
        direct_result = {
            "direct_height_cm": direct_height,
            "direct_std_cm": direct_std,
        }
    low_range_result = {}
    if low_range_regressor is not None:
        low_range_features = direct_regression_features(
            scores,
            measurement["tip_anchor_score"],
            measurement["top_anchor_score"],
            measurement["mid_anchor_score"],
        )
        low_range_height, low_range_std = _ensemble_regression_prediction(
            low_range_regressor, low_range_features
        )
        low_range_result = {
            "low_range_height_cm": low_range_height,
            "low_range_std_cm": low_range_std,
        }
    measurement.update({
        "available": True,
        "height_cm": height_cm,
        "evidence_gain": evidence_gain,
        **direct_result,
        **low_range_result,
    })
    return measurement


def _ensemble_regression_prediction(model, features: np.ndarray) -> tuple[float, float]:
    tree_predictions = np.asarray(
        [tree.predict(features)[0] for tree in model.estimators_]
    )
    return (
        float(np.clip(tree_predictions.mean(), 0, MAX_REPORTED_HEIGHT_CM)),
        float(tree_predictions.std()),
    )


def extract_runtime_scores(
    image_path: Path,
) -> dict[str, object]:
    calibration = load_calibration()
    templates = load_anchor_templates()
    gray = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None or gray.shape != (1080, 1920):
        return {"available": False}

    with np.load(REFERENCE_BUNDLE_PATH) as bundle:
        reference_roi = bundle["reference_roi"].copy()
        reference_anchors = {
            f"{name}_{field}": float(bundle[f"reference_{name}_{field}"])
            for name in ("tip", "top", "mid")
            for field in ("x_px", "y_px", "score")
        }
    target_anchors = locate_anchors(gray, templates)
    transform, alignment_mode = registration_transform(
        target_anchors, reference_anchors
    )
    if transform is None:
        return {
            "available": False,
            "alignment_mode": alignment_mode,
            **_anchor_result(target_anchors),
        }

    aligned_roi = align_peg_roi(gray, transform)
    return {
        "available": True,
        "scores": visibility_scores(aligned_roi, reference_roi, calibration),
        "alignment_mode": alignment_mode,
        **_anchor_result(target_anchors),
    }


def registration_transform(
    target: dict[str, float], reference: dict[str, float]
) -> tuple[np.ndarray | None, str]:
    if (
        target["top_score"] >= TWO_ANCHOR_MIN_SCORE
        and target["mid_score"] >= TWO_ANCHOR_MIN_SCORE
    ):
        return (
            similarity_transform(
                (target["top_x_px"], target["top_y_px"]),
                (target["mid_x_px"], target["mid_y_px"]),
                (reference["top_x_px"], reference["top_y_px"]),
                (reference["mid_x_px"], reference["mid_y_px"]),
            ),
            "top_mid_similarity",
        )
    visible_anchors = [
        name
        for name in ("tip", "top", "mid")
        if target[f"{name}_score"] >= SINGLE_ANCHOR_MIN_SCORE
    ]
    if visible_anchors:
        name = max(visible_anchors, key=lambda item: target[f"{item}_score"])
        return (
            translation_transform(
                (target[f"{name}_x_px"], target[f"{name}_y_px"]),
                (reference[f"{name}_x_px"], reference[f"{name}_y_px"]),
            ),
            f"{name}_translation",
        )
    return None, "unavailable"


def translation_transform(
    source: tuple[float, float], destination: tuple[float, float]
) -> np.ndarray:
    return np.asarray(
        [
            [1.0, 0.0, destination[0] - source[0]],
            [0.0, 1.0, destination[1] - source[1]],
        ],
        dtype=np.float64,
    )


def _anchor_result(anchors: dict[str, float]) -> dict[str, float]:
    return {
        "tip_anchor_score": anchors["tip_score"],
        "top_anchor_score": anchors["top_score"],
        "mid_anchor_score": anchors["mid_score"],
    }


def _gradient(gray: np.ndarray) -> np.ndarray:
    equalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gradient_x = cv2.Sobel(equalized, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(equalized, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gradient_x, gradient_y)


def _correlation(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape or first.size == 0:
        return float("nan")
    first_values = first.astype(np.float64).ravel()
    second_values = second.astype(np.float64).ravel()
    first_values -= first_values.mean()
    second_values -= second_values.mean()
    denominator = np.linalg.norm(first_values) * np.linalg.norm(second_values)
    if denominator < 1e-9:
        return 0.0
    return float(np.dot(first_values, second_values) / denominator)


def _subpixel_peak(
    response: np.ndarray, location: tuple[int, int]
) -> tuple[float, float]:
    x, y = location
    refined_x, refined_y = float(x), float(y)
    if 0 < x < response.shape[1] - 1:
        left, center, right = map(
            float, (response[y, x - 1], response[y, x], response[y, x + 1])
        )
        denominator = left - 2.0 * center + right
        if abs(denominator) > 1e-9:
            refined_x += 0.5 * (left - right) / denominator
    if 0 < y < response.shape[0] - 1:
        upper, center, lower = map(
            float, (response[y - 1, x], response[y, x], response[y + 1, x])
        )
        denominator = upper - 2.0 * center + lower
        if abs(denominator) > 1e-9:
            refined_y += 0.5 * (upper - lower) / denominator
    return refined_x, refined_y


def _linear_interpolate_with_extrapolation(
    value: float, coordinates: np.ndarray, samples: np.ndarray
) -> float:
    if value < coordinates[0]:
        first, second = 0, 1
    elif value > coordinates[-1]:
        first, second = -2, -1
    else:
        return float(np.interp(value, coordinates, samples))
    slope = (samples[second] - samples[first]) / (
        coordinates[second] - coordinates[first]
    )
    return float(samples[first] + slope * (value - coordinates[first]))
