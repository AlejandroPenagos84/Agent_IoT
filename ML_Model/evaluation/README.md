# Evaluation

Protocolo compartido por `02_tcp_vs_mqtt.ipynb` y `03_modelo_tcp.ipynb`: cualquier set
de features se evalúa con los mismos folds, el mismo XGBoost de hiperparámetros fijos
(`XGB_PARAMS`, sin Optuna) y el mismo `sample_weight` balanceado. Se usa como
`import evaluation as ev`; los imports pesados (xgboost, sklearn, matplotlib) son lazy.

| Módulo | Funciones |
|---|---|
| `scope.py` | `mqtt_scope` (vista 1883/8883), `binary_labels` (1 = DoS), `scope_overview` |
| `splits.py` | `find_grouped_splits` (StratifiedGroupKFold por `_connection`; reduce folds si alguno no tiene ambas clases o normal de todas las capturas), `fold_composition` |
| `models.py` | `XGB_PARAMS`, `make_xgb`, `fit_balanced` |
| `metrics.py` | `classification_metrics`, `false_positive_by_capture`, `metric_columns` |
| `baseline.py` | `trivial_rule_table` (reglas sin modelo; la primera fila es la línea base) |
| `compare.py` | `compare_feature_sets`, `summarize_folds`, `mean_importance` |
| `tls.py` | `tls_padding_sensitivity` (21–40 B sobre `frame.len` en test) |
| `decision.py` | `decide_a_vs_b` (criterio del plan), `leave_one_capture_out` |
| `plots.py` | `plot_fold_metrics`, `plot_fp_by_capture`, `plot_importance`, `plot_tls_sensitivity`, `plot_scope_vs_full`, `plot_confusion`, `plot_ablation`, `plot_univariate_auc` |
| `cv.py` | `cross_validate_oof` (predicciones out-of-fold), `subset_metrics` (métricas OOF por subconjunto, p. ej. vista `mqtt`), `confusion_table` |
| `ablation.py` | `ablation_sets` (B y variantes sin features), `ablation_deltas` + `interpret_drop` (> 0,03 depende, > 0,01 pierde algo), `univariate_auc_table` |

`ML_Model/export/` (`import export`) escribe y valida el modelo final B en
`modelos_agente_tcp/`: `export_tcp_model` y `validate_export`.
