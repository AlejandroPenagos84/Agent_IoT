from __future__ import annotations

import os
from typing import Sequence

from application.ports.ports_out import Classifier
from application.ports.types import FeatureRow

from ._common import (build_network_features, load_config, select_features,
                      validate_named_features)
from ._frame import to_frame


class TlsClassifier(Classifier):
    """Classify encrypted MQTT traffic with network-only XGBoost features."""
    def __init__(self, model_dir: str | None = None, device: str | None = None):
        """Load and validate the exported TLS model."""
        import joblib
        from xgboost import XGBClassifier

        self.model_dir = model_dir
        self.cfg = load_config(model_dir)
        self.le = joblib.load(os.path.join(model_dir, 'le_target.joblib'))
        self.xgb = XGBClassifier(enable_categorical=True)
        self.xgb.load_model(os.path.join(model_dir, 'xgb_tls.ubj'))

        validate_named_features(
            self.cfg['feature_columns_tls'],
            self.xgb.get_booster().feature_names,
            'TlsClassifier xgb_tls')

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        """Return labels for a window using only transport-derived features."""
        X = select_features(build_network_features(to_frame(window)),
                            self.cfg['feature_columns_tls'], 'TlsClassifier')
        pred = self.xgb.predict(X)
        return [str(label) for label in self.le.inverse_transform(pred)]
