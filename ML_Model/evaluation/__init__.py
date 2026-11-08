"""Protocolo de evaluación compartido por `02_tcp_vs_mqtt` y `03_modelo_tcp`.

Mismos folds, mismo XGBoost de hiperparámetros fijos y mismo `sample_weight`
balanceado para cualquier set de features. Imports pesados (xgboost, sklearn) son
lazy dentro de cada función.

- ``scope``: vista `mqtt` (puerto 1883/8883) y sus conteos.
- ``splits``: `StratifiedGroupKFold` por `_connection` con validación de folds.
- ``models``: hiperparámetros fijos y entrenamiento balanceado.
- ``metrics``: métricas binarias y FP por captura de origen del normal.
- ``baseline``: reglas triviales sin modelo.
- ``compare``: entrenamiento por fold de varios sets y resúmenes.
- ``tls``: sensibilidad aproximada al padding TLS.
- ``decision``: criterio de elección A vs B y leave-one-capture-out.
- ``cv``: validación cruzada con predicciones out-of-fold y métricas por subconjunto.
- ``ablation``: variantes de B, caídas frente a B y AUC univariada.
- ``plots``: gráficas de resultados.
"""

from .ablation import ablation_deltas, ablation_sets, interpret_drop, univariate_auc_table
from .baseline import trivial_rule_table
from .compare import compare_feature_sets, mean_importance, summarize_folds
from .cv import confusion_table, cross_validate_oof, subset_metrics
from .decision import decide_a_vs_b, leave_one_capture_out
from .metrics import classification_metrics, false_positive_by_capture, metric_columns
from .models import XGB_PARAMS, fit_balanced, make_xgb
from .plots import (plot_ablation, plot_confusion, plot_fold_metrics, plot_fp_by_capture,
                    plot_importance, plot_scope_vs_full, plot_tls_sensitivity,
                    plot_univariate_auc)
from .scope import MQTT_PORTS, binary_labels, mqtt_scope, scope_overview
from .splits import find_grouped_splits, fold_composition
from .tls import tls_padding_sensitivity
