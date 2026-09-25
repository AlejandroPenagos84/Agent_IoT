from __future__ import annotations

import os
from typing import Sequence

from application.ports.ports_out import Classifier
from application.ports.types import FeatureRow

from ._common import (CLASS_NAMES, build_lstm_raw, build_tensor,
                      crear_secuencias, load_config, load_known_origins,
                      load_known_topics, load_nan_statistics,
                      validate_class_contract, validate_named_features)
from ._frame import to_frame


class LstmClassifier(Classifier):
    """Supervised LSTM over sequences; class of the sequence's last row.

    The exported ``lstm_classifier.pt`` maps a sequence of ``SEQ_LEN`` tensor
    rows to four logits in ``CLASS_NAMES`` order. The autoencoder stays available
    as an auxiliary (``AnomalyClassifier``) and is not a public multiclass mode.
    """
    def __init__(self, model_dir: str | None = None, device: str | None = None):
        """Load the supervised LSTM, scaler and imputation contract."""
        import joblib
        import torch

        self.model_dir = model_dir
        self.cfg = load_config(model_dir)
        validate_class_contract(self.cfg)
        self.known_origins = load_known_origins(model_dir, self.cfg)
        self.known_topics = load_known_topics(model_dir, self.cfg)
        self.nan_statistics = load_nan_statistics(model_dir, self.cfg)
        self.scaler = joblib.load(os.path.join(model_dir, 'scaler.joblib'))
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.lstm = torch.jit.load(os.path.join(model_dir, 'lstm_classifier.pt'),
                                   map_location=self.device)
        self.lstm.eval()

        validate_named_features(
            self.cfg['feature_columns_lstm_raw'],
            getattr(self.scaler, 'feature_names_in_', None),
            'LstmClassifier scaler')

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        """Return one class label per reconstructed sequence."""
        import numpy as np
        import torch

        raw = build_lstm_raw(to_frame(window), self.cfg, self.known_origins,
                             self.known_topics)
        tensor = build_tensor(raw, self.scaler, self.nan_statistics,
                              'LstmClassifier tensor')
        xs, _ = crear_secuencias(tensor)
        if not len(xs):
            return []
        with torch.no_grad():
            logits = self.lstm(torch.tensor(xs, dtype=torch.float32).to(self.device))
            probabilities = torch.softmax(logits, dim=1).cpu().numpy()
        if not np.isfinite(probabilities).all():
            raise ValueError('LstmClassifier: probabilidades no finitas; '
                             'no se emite etiqueta')
        predicted = probabilities.argmax(axis=1)
        return [CLASS_NAMES[int(index)] for index in predicted]
