# Plan — `02_tcp_vs_mqtt.ipynb`

## Objetivo

Comparar de forma controlada la opción **A (features MQTT en claro)** contra la
opción **B (solo features TCP)** y dejar documentada la decisión de usar B.

**Este notebook es solo A vs B.** No incluye A'. No incluye ablaciones de B; esas
se mueven al notebook 3.

## Entradas

- `ML_Model/artifacts/df_raw.joblib` (generado por `01_eda_politica.ipynb`).
- `ML_Model/data_preprocessing/tcp_features.py` (`TCP_FEATURE_COLUMNS`,
  `build_tcp_features`).
- `ML_Model/data_preprocessing/feature_engineering.py` (`FEATURE_COLUMNS`).
- `ML_Model/data_preprocessing/load_data.py` (`TARGET_COL`).

## Salidas

- Tablas y figuras de la comparación A/B.
- Conclusión escrita: B es el set final.
- No se exportan modelos ni artefactos de agente.

## Celdas de origen

Copiar y adaptar las celdas **30–41** del notebook actual:

| Celdas | Contenido |
|---|---|
| 30–31 | Construcción de features A y de la matriz A |
| 32–33 | 2.8 Alcance MQTT (`df_scope` 1883/8883) |
| 34–39 | 2.9 Comparación A/B, métricas, importancia y TLS |
| 40–41 | 2.9.5 Diagnóstico A/B sobre todo el tráfico |

Las celdas 42–50 (ablaciones 2.10/2.11) **no van aquí**; se mueven al notebook 3.

## Eliminación de A'

Hay que quitar A' de todas las celdas y del texto:

- No construir `X_scope_ap`.
- No incluir la clave `"A'"` en `compare_feature_sets`.
- No incluir filas de A' en `scope_summary`, `scope_means` ni en las tablas de
  decisión.
- No incluir A' en el diagnóstico sobre todo el tráfico.
- No mencionar A' en el markdown ni en las conclusiones.

El notebook debe quedar estrictamente con los sets `A` y `B`.

## Contenido técnico

1. Cargar `df_raw.joblib` y verificar columnas y conteos.
2. Construir:
   - `X_scope_a = build_feature_matrix(df_scope)` (13 features MQTT).
   - `X_scope_b = build_tcp_features(df_scope)` (12 features TCP).
3. Filtrar `df_scope` por puerto 1883/8883.
4. Definir línea base trivial dentro de `df_scope`:
   - siempre normal;
   - siempre DoS;
   - cliente → broker;
   - broker → cliente;
   - capa MQTT;
   - cliente → broker o capa MQTT.
5. Folds `StratifiedGroupKFold` por `_connection`; intentar 5 y reducir si algún
   fold no tiene ambas clases o normal de las tres capturas.
6. Modelo XGBoost con hiperparámetros fijos e iguales para A y B:
   `n_estimators=300`, `learning_rate=0.05`, `max_depth=4`,
   `min_child_weight=2.0`, `subsample=0.9`, `colsample_bytree=0.9`,
   `reg_lambda=1.0`, `tree_method='hist'`.
7. `sample_weight` balanceado.
8. Métricas por fold: macro-F1, balanced accuracy, ROC-AUC, recall de DoS y FP
   por captura de origen del normal (DoS, MitM, Intrusion).
9. Importancia media de features de A y B.
10. Sensibilidad TLS aproximada: sumar 21–40 bytes a `frame.len` y
    `fe_log_len` en test y medir la caída de B.
11. Diagnóstico A/B sobre todo el tráfico (`df_raw`), sin A'.
12. Conclusión con el criterio del plan:
    - B si su macro-F1 queda a ≤ 0,03 de A, supera la línea base y no aumenta
      los FP en ninguna captura.
    - A en caso contrario, documentando que solo vale para MQTT en claro.

## Resultados esperados (referencia)

En `df_scope`:

| Set | Macro-F1 |
|---|---:|
| A | 0,9778 |
| B | 0,9962 |

En todo el tráfico:

| Set | Macro-F1 |
|---|---:|
| A | 0,9915 |
| B | 0,9981 |

La conclusión esperada es B.

## Criterios de aceptación

- No aparece A' en código, tablas ni markdown.
- A y B usan exactamente los mismos folds, hiperparámetros y `sample_weight`.
- La línea base y los FP por captura se reportan.
- La conclusión B queda escrita y justificada.
- El notebook carga el artefacto de notebook 1 y no reconstruye la limpieza.
