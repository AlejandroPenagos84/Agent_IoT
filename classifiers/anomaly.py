from __future__ import annotations

from typing import Sequence

from core.types import FeatureRow

from ._frame import to_frame

from agent_inference import MQTTDetector
LABEL_NORMAL = 'normal'
LABEL_ANOMALY = 'ataque'


class AnomalyClassifier:
    def __init__(self, model_dir: str | None = None, detector=None,
                 device: str | None = None):
        if detector is not None:
            self._det = detector
        else:
            
            self._det = MQTTDetector(model_dir, device=device)

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        flags = self._det.predecir_anomalia(to_frame(window))
        return [LABEL_ANOMALY if int(flag) == 1 else LABEL_NORMAL for flag in flags]
