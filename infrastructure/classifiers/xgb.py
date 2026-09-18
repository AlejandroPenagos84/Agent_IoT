from __future__ import annotations

import os
from typing import Sequence

from application.ports.ports_out import Classifier
from application.ports.types import FeatureRow

from ._common import build_case1, load_config, validate_named_features
from ._frame import to_frame


class XgbClassifier(Classifier):
    """Classify the full MQTTset feature representation with XGBoost."""
    def __init__(self, model_dir: str | None = None, device: str | None = None):
        """Load and validate the exported full-feature model."""
        import joblib
        from xgboost import XGBClassifier

        self.model_dir = model_dir
        self.cfg = load_config(model_dir)
        self.le = joblib.load(os.path.join(model_dir, 'le_target.joblib'))
        self.xgb = XGBClassifier(enable_categorical=True)
        self.xgb.load_model(os.path.join(model_dir, 'xgb_case1.ubj'))

        validate_named_features(
            self.cfg['feature_columns_case1'],
            self.xgb.get_booster().feature_names,
            'XgbClassifier xgb_case1')

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        """Return labels predicted for the supplied feature window."""
        X = build_case1(to_frame(window), self.cfg)
        pred = self.xgb.predict(X)
        return [str(label) for label in self.le.inverse_transform(pred)]
