"""Build a portable offline Windows app with CPU-only PyTorch installed."""
from __future__ import annotations

import hashlib
import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    import torch
    from torchvision.models import ResNet18_Weights

    if sys.platform != "win32" or torch.version.cuda is not None:
        raise RuntimeError("Auf Windows mit der CPU-Version von PyTorch bauen.")
    weights = ResNet18_Weights.IMAGENET1K_V1
    weights.get_state_dict(progress=True, check_hash=True)
    source = Path(torch.hub.get_dir()) / "checkpoints" / Path(weights.url).name
    if not hashlib.sha256(source.read_bytes()).hexdigest().startswith("f37072fd"):
        raise RuntimeError("Die ResNet-Gewichte haben nicht die erwartete Prüfsumme.")
    target = ROOT / "height_model" / "resources" / source.name
    shutil.copy2(source, target)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--onedir", "--name", "Schneepegel Brotenau", "--icon", "desktop/app.ico",
        "--add-data", "desktop/app.ico:desktop",
        "--add-data", "height_model/artifacts:height_model/artifacts",
        "--add-data", "height_model/resources:height_model/resources",
        "--add-data", "quality_model/artifacts:quality_model/artifacts",
        "--collect-submodules", "sklearn.ensemble",
        "--collect-submodules", "sklearn.linear_model",
        "--hidden-import", "sklearn.neighbors._partition_nodes",
        "schneepegel.py",
    ], cwd=ROOT, check=True)
    destination = ROOT / "dist" / "Schneepegel Brotenau"
    shutil.copy2(ROOT / "START.txt", destination)
    licenses = destination / "Drittanbieter-Lizenzen"
    for package in importlib.metadata.distributions():
        for file in package.files or []:
            if ".dist-info" in str(file) and any(s in str(file).lower() for s in ("license", "copying", "notice")):
                installed = package.locate_file(file)
                if installed.is_file():
                    folder = licenses / package.metadata["Name"]
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(installed, folder / Path(file).name)
    (destination / "Drittanbieter.txt").write_text(
        "Diese Anwendung verwendet Python, PySide6/Qt, PyTorch/torchvision, NumPy, SciPy, "
        "scikit-learn, OpenCV, Pillow, joblib und threadpoolctl.\n"
        "Lizenztexte liegen im Ordner Drittanbieter-Lizenzen und bei den Bibliotheken unter _internal.\n"
        "PySide6 und Qt werden als austauschbare dynamische Bibliotheken mitgeliefert.\n"
        "Quellcode der Bibliotheken: https://code.qt.io/ · https://github.com/pyside/pyside-setup · "
        "https://github.com/pytorch/pytorch · https://github.com/pytorch/vision\n"
        "Quellcode der Anwendung: https://github.com/Dolcruz/schneepegel-brotenau\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
