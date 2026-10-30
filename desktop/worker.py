from pathlib import Path

from PySide6.QtCore import QThread, Signal


class AnalysisWorker(QThread):
    current = Signal(int, str)
    result = Signal(int, dict)
    failed = Signal(str)

    def __init__(self, jobs: list[tuple[int, str]], parent=None):
        super().__init__(parent)
        self.jobs = jobs

    def run(self):
        try:
            # Heavy imports and model initialization belong off the UI thread.
            import cv2
            import torch
            from threadpoolctl import threadpool_limits
            from height_model.predict_pipeline import HERE, SnowAnalyzer

            torch.set_num_threads(2)
            # set_num_interop_threads may only be called once in a process.
            if not getattr(AnalysisWorker, "interop_configured", False):
                torch.set_num_interop_threads(1)
                AnalysisWorker.interop_configured = True
            cv2.setNumThreads(1)
            weights = HERE / "resources" / "resnet18-f37072fd.pth"
            with threadpool_limits(limits=2):
                analyzer = SnowAnalyzer(weights)
                for regressor in (
                    analyzer.models["positive_height_regressor"],
                    analyzer.direct_regressor,
                    analyzer.low_range_regressor,
                ):
                    regressor.n_jobs = 1
                for index, filename in self.jobs:
                    if self.isInterruptionRequested():
                        break
                    self.current.emit(index, Path(filename).name)
                    try:
                        result = analyzer.predict(Path(filename))
                    except (OSError, ValueError, RuntimeError) as exc:
                        result = {"status": "error", "snow_height_cm": None, "reason": str(exc)}
                    self.result.emit(index, result)
        except Exception as exc:
            self.failed.emit(f"Die Analyse konnte nicht gestartet werden.\n\n{exc}")
