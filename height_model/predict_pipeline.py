from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import torch
from PIL import Image
from torch import nn
from torchvision.models import ResNet18_Weights, resnet18

from features import extract_context_features, extract_peg_profile, load_anchor_template
from geometric_meter import measure_geometric_height


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
QUALITY_MODEL_DIR = ROOT / "quality_model"


def quantize_height(height_cm: float, resolution_cm: float) -> float:
    return float(np.round(height_cm / resolution_cm) * resolution_cm)


def geometric_route_flags(
    geometric: dict,
    direct_metadata: dict,
    low_metadata: dict,
    geometric_metadata: dict,
) -> dict[str, bool]:
    flags = {
        "direct_candidate": False,
        "direct_specialist": False,
        "high_candidate": False,
        "high_specialist": False,
        "low_candidate": False,
        "low_specialist": False,
        "geometric_specialist": False,
    }
    if not geometric.get("available"):
        return flags

    raw_height = float(geometric["height_cm"])
    direct_height = float(geometric["direct_height_cm"])
    direct_std = float(geometric["direct_std_cm"])
    low_height = float(geometric["low_range_height_cm"])
    low_std = float(geometric["low_range_std_cm"])
    maximum_anchor_score = max(
        float(geometric["tip_anchor_score"]),
        float(geometric["top_anchor_score"]),
        float(geometric["mid_anchor_score"]),
    )

    flags["direct_candidate"] = bool(
        direct_height >= direct_metadata["specialist_min_prediction_cm"]
        and raw_height >= direct_metadata["minimum_geometric_height_cm"]
    )
    flags["direct_specialist"] = bool(
        flags["direct_candidate"]
        and direct_std <= direct_metadata["specialist_max_std_cm"]
        and abs(direct_height - raw_height)
        <= direct_metadata["maximum_geometric_disagreement_cm"]
    )
    flags["high_candidate"] = bool(
        raw_height >= geometric_metadata["high_range_min_height_cm"]
    )
    flags["high_specialist"] = bool(
        flags["high_candidate"]
        and maximum_anchor_score >= geometric_metadata["single_anchor_min_score"]
        and float(geometric["evidence_gain"])
        >= geometric_metadata["high_evidence_gain_min"]
        and direct_height >= geometric_metadata["high_direct_min_prediction_cm"]
        and direct_std <= geometric_metadata["high_direct_max_std_cm"]
        and abs(direct_height - raw_height)
        <= geometric_metadata["high_direct_max_disagreement_cm"]
    )
    flags["low_candidate"] = bool(
        low_height >= low_metadata["specialist_min_prediction_cm"]
        and low_height < low_metadata["specialist_max_prediction_cm"]
        and raw_height >= low_metadata["minimum_geometric_height_cm"]
    )
    flags["low_specialist"] = bool(
        flags["low_candidate"]
        and low_std <= low_metadata["specialist_max_std_cm"]
        and abs(low_height - raw_height)
        <= low_metadata["maximum_geometric_disagreement_cm"]
    )
    flags["geometric_specialist"] = bool(
        raw_height >= geometric_metadata["specialist_min_height_cm"]
        and float(geometric["top_anchor_score"])
        >= geometric_metadata["top_clarity_min"]
        and float(geometric["mid_anchor_score"])
        >= geometric_metadata["mid_clarity_min"]
    )
    return flags


def geometric_diagnostics(geometric: dict) -> dict:
    if not geometric.get("available"):
        return {
            "geometric_available": False,
            "alignment_mode": geometric.get("alignment_mode", "unavailable"),
        }
    return {
        "geometric_available": True,
        "raw_geometric_height_cm": float(geometric["height_cm"]),
        "geometric_evidence_gain": float(geometric["evidence_gain"]),
        "direct_prediction_cm": float(geometric["direct_height_cm"]),
        "direct_prediction_std_cm": float(geometric["direct_std_cm"]),
        "low_range_prediction_cm": float(geometric["low_range_height_cm"]),
        "low_range_prediction_std_cm": float(geometric["low_range_std_cm"]),
        "alignment_mode": str(geometric["alignment_mode"]),
        "tip_anchor_score": float(geometric["tip_anchor_score"]),
        "top_anchor_score": float(geometric["top_anchor_score"]),
        "mid_anchor_score": float(geometric["mid_anchor_score"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kontext- und pegelbasierte Schneehöhenschätzung."
    )
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()

    models = joblib.load(HERE / "artifacts" / "combined_height_model.joblib")
    metadata = json.loads(
        (HERE / "artifacts" / "combined_metadata.json").read_text(encoding="utf-8")
    )
    geometric_classifier = joblib.load(
        HERE / "artifacts" / "geometric_visibility_classifier.joblib"
    )
    direct_regressor = joblib.load(
        HERE / "artifacts" / "full_range_height_regressor.joblib"
    )
    direct_metadata = json.loads(
        (HERE / "artifacts" / "full_range_height_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    low_range_regressor = joblib.load(
        HERE / "artifacts" / "low_range_height_regressor.joblib"
    )
    low_metadata = json.loads(
        (HERE / "artifacts" / "low_range_height_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    geometric_metadata = json.loads(
        (HERE / "artifacts" / "geometric_metadata.json").read_text(encoding="utf-8")
    )
    template = load_anchor_template()
    quality_classifier = joblib.load(QUALITY_MODEL_DIR / "artifacts" / "classifier.joblib")
    quality_metadata = json.loads(
        (QUALITY_MODEL_DIR / "artifacts" / "metadata.json").read_text(encoding="utf-8")
    )
    quality_weights = ResNet18_Weights.IMAGENET1K_V1
    quality_encoder = resnet18(weights=quality_weights)
    quality_encoder.fc = nn.Identity()
    quality_encoder.eval()
    resolution_cm = float(metadata["output_resolution_cm"])

    for image in args.images:
        with Image.open(image) as source:
            quality_tensor = quality_weights.transforms()(
                source.convert("RGB")
            ).unsqueeze(0)
        with torch.inference_mode():
            quality_embedding = quality_encoder(quality_tensor).numpy()
        probability_unusable = float(
            quality_classifier.predict_proba(quality_embedding)[0, 1]
        )
        if probability_unusable >= float(quality_metadata["threshold"]):
            print(
                json.dumps(
                    {
                        "image": str(image.resolve()),
                        "status": "unusable",
                        "snow_height_cm": None,
                        "probability_unusable": probability_unusable,
                        "reason": "quality_filter",
                    },
                    ensure_ascii=False,
                )
            )
            continue

        geometric = measure_geometric_height(
            image,
            geometric_classifier,
            direct_regressor,
            low_range_regressor,
        )
        flags = geometric_route_flags(
            geometric, direct_metadata, low_metadata, geometric_metadata
        )
        context = extract_context_features(image)[None, :]
        probability_zero = float(models["zero_classifier"].predict_proba(context)[0, 1])
        result = {
            "image": str(image.resolve()),
            "probability_unusable": probability_unusable,
            "probability_zero_cm": probability_zero,
            **geometric_diagnostics(geometric),
        }

        if probability_zero >= metadata["zero_threshold"]:
            result.update(
                status="measured", snow_height_cm=0.0, reason="clear_zero_context"
            )
        elif probability_zero >= metadata["context_ambiguous_lower"]:
            result.update(
                status="uncertain",
                snow_height_cm=None,
                reason="ambiguous_zero_context",
            )
        elif flags["direct_specialist"]:
            result.update(
                status="measured",
                snow_height_cm=quantize_height(
                    float(geometric["direct_height_cm"]), resolution_cm
                ),
                reason="calibrated_direct_geometric_specialist",
            )
        elif flags["high_specialist"]:
            result.update(
                status="measured",
                snow_height_cm=quantize_height(
                    float(geometric["height_cm"]), resolution_cm
                ),
                reason="calibrated_high_range_specialist",
            )
        elif flags["low_specialist"]:
            result.update(
                status="measured",
                snow_height_cm=quantize_height(
                    float(geometric["low_range_height_cm"]), resolution_cm
                ),
                reason="calibrated_low_range_specialist",
            )
        elif any(
            flags[name]
            for name in (
                "direct_candidate",
                "high_candidate",
                "low_candidate",
                "geometric_specialist",
            )
        ):
            result.update(
                status="uncertain",
                snow_height_cm=None,
                reason="geometric_models_disagree",
            )
        else:
            profile, anchor_score = extract_peg_profile(image, template)
            regressor = models["positive_height_regressor"]
            tree_predictions = np.asarray(
                [tree.predict(profile[None, :])[0] for tree in regressor.estimators_]
            )
            prediction = float(np.clip(tree_predictions.mean(), 0, 80))
            prediction_std = float(tree_predictions.std())
            result.update(
                anchor_score=anchor_score,
                prediction_std_cm=prediction_std,
            )
            if prediction_std > metadata["height_std_threshold_cm"]:
                result.update(
                    status="uncertain",
                    snow_height_cm=None,
                    reason="height_disagreement",
                )
            else:
                result.update(
                    status="measured",
                    snow_height_cm=quantize_height(prediction, resolution_cm),
                    reason="positive_peg_model",
                )
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
