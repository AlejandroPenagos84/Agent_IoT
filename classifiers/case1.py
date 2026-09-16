from __future__ import annotations

from typing import Sequence

from core.types import FeatureRow

from ._frame import to_frame

from agent_inference import MQTTDetector
class Case1Classifier:
    def __init__(self, model_dir: str | None = None, detector=None,
                 device: str | None = None):
        if detector is not None:
            self._det = detector
        else:
            
            self._det = MQTTDetector(model_dir, device=device)

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        labels = self._det.predecir_caso1(to_frame(window))
        return [str(label) for label in labels]
