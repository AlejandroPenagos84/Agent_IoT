from __future__ import annotations

import os
from typing import Sequence

from application.ports.ports_out import Classifier
from application.ports.types import FeatureRow

from ._common import (build_lstm_raw, crear_secuencias, load_config, recon_mse,
                      select_features, validate_named_features)
from ._frame import to_frame


class HybridClassifier(Classifier):
    """Combine LSTM reconstruction error with XGBoost classification."""
    def __init__(self, model_dir: str | None = None, device: str | None = None):
        """Load and validate all artifacts required by the hybrid pipeline."""
        import joblib
        import torch
        from xgboost import XGBClassifier

        self.model_dir = model_dir
        self.cfg = load_config(model_dir)
        self.le = joblib.load(os.path.join(model_dir, 'le_target.joblib'))
        self.scaler = joblib.load(os.path.join(model_dir, 'scaler.joblib'))
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.xgb = XGBClassifier(enable_categorical=True)
        self.xgb.load_model(os.path.join(model_dir, 'xgb_hybrid.ubj'))
        self.lstm = torch.jit.load(os.path.join(model_dir, 'lstm_ae.pt'),
                                   map_location=self.device)
        self.lstm.eval()

        validate_named_features(
            self.cfg['feature_columns_lstm_raw'],
            getattr(self.scaler, 'feature_names_in_', None),
            'HybridClassifier scaler')
        validate_named_features(
            self.cfg['feature_columns_hybrid'],
            self.xgb.get_booster().feature_names,
            'HybridClassifier xgb_hybrid')

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        """Return labels predicted from network features and LSTM MSE."""
        raw = build_lstm_raw(to_frame(window), self.cfg)
        scaled = self.scaler.transform(raw)
        xs, end_idx = crear_secuencias(scaled)
        mse = recon_mse(self.lstm, xs, self.device)
        X = raw.iloc[end_idx].copy().reset_index(drop=True)
        X['fe_lstm_mse'] = mse
        X = select_features(X, self.cfg['feature_columns_hybrid'],
                            'HybridClassifier')
        pred = self.xgb.predict(X)
        return [str(label) for label in self.le.inverse_transform(pred)]
