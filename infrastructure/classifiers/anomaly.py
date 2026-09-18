from __future__ import annotations

import os
from typing import Sequence

from application.ports.ports_out import Classifier
from application.ports.types import FeatureRow

from ._common import (build_lstm_raw, crear_secuencias, load_config, recon_mse,
                      validate_named_features)
from ._frame import to_frame

LABEL_NORMAL = 'normal'
LABEL_ANOMALY = 'ataque'


class AnomalyClassifier(Classifier):
    """Classify windows as ``normal`` or ``ataque`` using LSTM reconstruction error."""
    def __init__(self, model_dir: str | None = None, device: str | None = None):
        """Load the autoencoder, scaler, threshold, and selected Torch device."""
        import joblib
        import torch

        self.model_dir = model_dir
        self.cfg = load_config(model_dir)
        self.scaler = joblib.load(os.path.join(model_dir, 'scaler.joblib'))
        self.threshold = self.cfg['threshold']
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.lstm = torch.jit.load(os.path.join(model_dir, 'lstm_ae.pt'),
                                   map_location=self.device)
        self.lstm.eval()

        validate_named_features(
            self.cfg['feature_columns_lstm_raw'],
            getattr(self.scaler, 'feature_names_in_', None),
            'AnomalyClassifier scaler')

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        """Return one anomaly label for each reconstructed sequence."""
        raw = build_lstm_raw(to_frame(window), self.cfg)
        scaled = self.scaler.transform(raw)
        xs, _ = crear_secuencias(scaled)
        mse = recon_mse(self.lstm, xs, self.device)
        return [LABEL_ANOMALY if int(flag) == 1 else LABEL_NORMAL
                for flag in (mse > self.threshold).astype(int)]
