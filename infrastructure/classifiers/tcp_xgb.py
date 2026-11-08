from __future__ import annotations

import os
from typing import Sequence

from application.ports.ports_out import Classifier
from application.ports.types import FeatureRow

from ._common import load_config, validate_named_features

'''
XGBoost classifier over the 12 causal TCP features (model B). The capture sidecar
already computes those features per frame (`tcp_features` in the JSONL), so the
model scores each row independently; the window only groups rows by flow.
'''

MODEL_FILE = 'xgb_tcp.ubj'


class TcpXgbClassifier(Classifier):
    """Load `modelos_agente_tcp/` and label every row of the window."""

    def __init__(self, model_dir: str | None = None, threshold: float = 0.5):
        """Load and validate the exported TCP model, encoder and contract."""
        import joblib
        from xgboost import XGBClassifier

        if not model_dir:
            raise ValueError('TcpXgbClassifier necesita model_dir (modelos_agente_tcp)')
        self.cfg = load_config(model_dir)
        if self.cfg.get('feature_mode') != 'tcp':
            raise ValueError(f'{model_dir}: feature_mode={self.cfg.get("feature_mode")!r}; '
                             'TcpXgbClassifier necesita artefactos de 03_modelo_tcp.ipynb')
        self.columns = list(self.cfg['feature_columns_tcp'])
        self.threshold = threshold
        self.le = joblib.load(os.path.join(model_dir, 'le_target.joblib'))
        if list(self.le.classes_) != list(self.cfg['class_names']):
            raise ValueError(f'le_target {list(self.le.classes_)} != class_names '
                             f'{self.cfg["class_names"]}')
        self.xgb = XGBClassifier()
        self.xgb.load_model(os.path.join(model_dir, self.cfg.get('model_file', MODEL_FILE)))
        validate_named_features(self.columns, self.xgb.get_booster().feature_names,
                                'TcpXgbClassifier xgb_tcp')
        self._booster = self.xgb.get_booster()
        self._booster.feature_names = None   # entrada numpy en el orden validado
        self._booster.set_param({'nthread': 1})

    def _matrix(self, window: Sequence[FeatureRow]):
        """Rows in model column order as a float numpy array (no pandas per frame)."""
        import numpy as np

        fill = float(self.cfg.get('nan_fill', 0.0))
        missing = [c for c in self.columns if c not in window[0]]
        if missing:
            raise ValueError(f'TcpXgbClassifier: faltan features TCP {missing}; '
                             'reconstruye el sidecar capture (tcp_features en el JSONL)')
        matrix = np.array([[row.get(c, fill) for c in self.columns] for row in window],
                          dtype=float)
        return np.where(np.isfinite(matrix), matrix, fill)

    def predict_proba(self, window: Sequence[FeatureRow]) -> list[float]:
        """Probability of `ataque` for each row."""
        if not window:
            return []
        # inplace_predict con un hilo: mucho más rápido que predict_proba para 1 fila.
        return [float(p) for p in self._booster.inplace_predict(self._matrix(window))]

    def predict(self, window: Sequence[FeatureRow]) -> list[str]:
        """Label each row with `normal`/`ataque` using ``threshold``."""
        normal_idx = int(self.cfg.get('normal_idx', 0))
        attack_idx = 1 - normal_idx
        codes = [attack_idx if p >= self.threshold else normal_idx
                 for p in self.predict_proba(window)]
        return [str(label) for label in self.le.inverse_transform(codes)]
