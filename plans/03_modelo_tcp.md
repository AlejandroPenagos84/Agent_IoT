# Plan — `03_modelo_tcp.ipynb`

## Objetivo

Entrenar, evaluar y exportar el **modelo final B, solo con features TCP**.
Además, este notebook recibe las ablaciones 2.10 y 2.11, adaptadas **sin A'**,
para medir la robustez de B antes de exportar.

## Entradas

- `ML_Model/artifacts/df_raw.joblib` (generado por `01_eda_politica.ipynb`).
- `ML_Model/data_preprocessing/tcp_features.py` (`TCP_FEATURE_COLUMNS`,
  `build_tcp_features`).
- `ML_Model/data_preprocessing/load_data.py` (`TARGET_COL`).

## Salidas

Directorio `modelos_agente_tcp/`:

- `xgb_tcp.ubj`
- `le_target.joblib`
- `pipeline_config.json`
- `metrics.json`
- `evaluation_split.json`
- `manifest.json`

Después de validar que los artefactos cargan y predicen igual que el notebook,
se reemplaza `modelos_agente/` por `modelos_agente_tcp/`.

## Estructura del notebook

### 1. Configuración y carga

- Imports y constantes: `SEED`, `MODEL_DIR='modelos_agente_tcp'`.
- Cargar `df_raw.joblib`.
- Verificar etiquetas `normal`/`DoS`, conteos y columnas de contexto.

### 2. Features TCP

- `X_tcp = build_tcp_features(df_raw)`.
- Verificar:
  - columnas exactas e iguales a `TCP_FEATURE_COLUMNS`;
  - sin NaN ni infinitos;
  - 12 features, sin IP, puertos crudos ni `frame.time_epoch`.
- Etiquetas binarias: `normal=0`, `ataque=1` (donde `ataque` es DoS).

### 3. Modelo final B

- XGBoost con hiperparámetros **fijos**, sin Optuna:
  `n_estimators=300`, `learning_rate=0.05`, `max_depth=4`,
  `min_child_weight=2.0`, `subsample=0.9`, `colsample_bytree=0.9`,
  `reg_lambda=1.0`, `tree_method='hist'`, `random_state=SEED`,
  `eval_metric='logloss'`.
- `sample_weight` balanceado.
- Evaluación con `StratifiedGroupKFold` por `_connection` (5 folds; reducir y
  documentar si falta cobertura).
- Métricas: macro-F1, balanced accuracy, ROC-AUC, recall de DoS, precisión de
  DoS, recall normal y FP por captura de origen.
- Importancia media de features.
- Refit final sobre todos los datos limpios con los mismos hiperparámetros y
  exportación de ese modelo.

### 4. Ablaciones movidas desde 2.10/2.11

Adaptar las celdas 42–50 del notebook actual, **sin A'**:

- **2.10 sobre todo el tráfico:** B vs B sin `tcp_new_conns_5s`. A puede
  aparecer solo como referencia; A' nunca.
- **2.11 en `df_scope`:** B, B sin `tcp_new_conns_5s`, B sin
  `tcp_new_conns_5s` y `tcp_asymmetry_5s`. A puede aparecer como referencia;
  A' nunca.
- Tabla de AUC univariada en full y scope.
- Interpretación: si B cae > 0,03 al quitar una feature, depende de ella; si no,
  la señal está repartida.

### 5. Exportación

`pipeline_config.json` debe incluir como mínimo:

```json
{
  "dataset": "MQTT_UAD/DoS.csv",
  "task": "dos_binary",
  "positive_class": "DoS",
  "feature_mode": "tcp",
  "feature_columns_tcp": ["frame.len", "..."],
  "class_names": ["normal", "ataque"],
  "normal_idx": 0,
  "window_size": 11,
  "seq_len": 10,
  "nan_fill": -1.0,
  "split_strategy": "grouped_by_connection",
  "hyperparameters": {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 4,
    "min_child_weight": 2.0,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "reg_lambda": 1.0
  }
}
```

`metrics.json` guarda los resultados por fold y la media ± std.
`evaluation_split.json` identifica las filas y las particiones.
`manifest.json` guarda hash, fecha, columnas, conteos y versión.

### 6. Validación antes de reemplazar `modelos_agente/`

- Cargar `xgb_tcp.ubj`, `le_target.joblib` y `pipeline_config.json`.
- Predecir una muestra del notebook y comparar con el modelo en memoria.
- Verificar que el orden de columnas coincide con `TCP_FEATURE_COLUMNS`.
- Si todo coincide, reemplazar `modelos_agente/`.

## Lo que no debe incluir

- A' en ninguna celda, tabla o conclusión.
- Features `mqtt.*` en el modelo final.
- El export A de las celdas 51–64.
- Optuna, LSTM o híbrido A (quedan solo en el backup).

## Criterios de aceptación

- El notebook corre de arriba a abajo desde `df_raw.joblib`.
- `X_tcp` tiene 12 columnas, sin NaN/inf y en el orden de `TCP_FEATURE_COLUMNS`.
- El modelo final usa solo features TCP.
- Las ablaciones se reproducen sin A'.
- `modelos_agente_tcp/` contiene todos los artefactos y cargan correctamente.
- La sustitución de `modelos_agente/` se hace solo después de la validación.
- `python -m unittest discover -s tests -v` sigue pasando.

## Nota de alcance

Este notebook exporta el modelo, pero **no implementa** el builder incremental de
features TCP ni el adaptador `TcpXgbClassifier` del agente. Eso es una fase
posterior: el agente actual sigue esperando artefactos MQTT y no debe modificarse
en esta reorganización.
