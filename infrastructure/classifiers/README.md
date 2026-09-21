# `classifiers/` — Classifiers (Adapters)

Adaptadores que implementan `application.ports.ports_out.Classifier`
(`predict(window: Sequence[FeatureRow]) -> list[str]`). Envuelven los artefactos
ML exportados por `ml-mqtt-model.ipynb` (patrón **Adapter**/**Strategy**).

`predict` devuelve **una etiqueta por frame evaluable**; el agente toma la
**última** (`labels[-1]`), la fila más reciente de la ventana.
Los clasificadores LSTM incluyen la última secuencia completa: con 11 filas y
`SEQ_LEN = 10` evalúan dos secuencias, y la última termina en el frame cuyo
contexto utiliza la alerta. Esta corrección no cambia features ni artefactos.

Los imports pesados (`torch`, `xgboost`, `joblib`, `pandas`) son **lazy** dentro
de `__init__`/`predict` para que importar el paquete no exija esas dependencias.

## Contrato de features (MQTT en claro)

`_common.build_mqtt_features` es el espejo de `build_mqtt_features` de
`ml-mqtt-model.ipynb`: 13 features compactas para frames TCP y L2,
**sin `tcp.srcport`/`tcp.dstport` crudos** y sin columnas de identidad, reloj de
captura ni duplicados. En frames L2 los campos MQTT/puertos ausentes siguen la
imputación `nan_fill` declarada en `pipeline_config.json`.

| Grupo | Columnas |
|---|---|
| Red (`COLS_RED`) | `frame.len`, `frame.time_delta` |
| Red derivadas | `fe_bytes_per_sec`, `fe_is_standard_mqtt_port`, `fe_is_broker_to_client`, `fe_log_len` |
| MQTT crudas | `mqtt.hdrflags`, `mqtt.len`, `mqtt.topic_len` |
| MQTT derivadas | `fe_msg_entropy`, `fe_topic_entropy`, `fe_topic_depth`, `fe_payload_ratio` |

Los puertos se usan **solo** para las banderas `fe_is_*`, nunca como feature.
El orden de columnas lo manda `modelos_agente/pipeline_config.json`; cada
clasificador **valida al cargar** que el modelo/scaler espera exactamente esas
features (`_common.validate_named_features`) y falla temprano con un mensaje
claro si hay que reentrenar/reexportar.

El objetivo es **binario** (`class_names = ['normal', 'ataque']`); el agente
rechaza artefactos con otra lista de clases (`composition_root.build_agent`).

## `_common.py`

- `load_config(model_dir)` — lee `pipeline_config.json`.
- `select_features(df, cols, where)` — selecciona en el orden del config; error
  explícito si falta una columna.
- `validate_named_features(expected, actual, where)` — compara config vs
  `scaler.feature_names_in_` / `xgb.get_booster().feature_names`.
- `build_network_features` / `build_mqtt_features` — features del contrato.
- `build_case1` / `build_lstm_raw` — subset MQTT para XGBoost y LSTM.
- `crear_secuencias` / `recon_mse` — ventanas (`SEQ_LEN = 10`) y MSE del LSTM.

## `_frame.py`

- `to_frame(window)` — convierte la ventana de `FeatureRow` en un `DataFrame`
  con el orden canónico de `infrastructure/tshark/tshark_schema.py`; IP, MAC y
  `tcp.stream` permanecen fuera de esa matriz.

## `hybrid.py` — `HybridClassifier`

- XGBoost híbrido: features MQTT compactas + `fe_lstm_mse` (error del LSTM AE).
- Modelo por defecto del agente (`composition_root.build_agent`).
- Valida `feature_columns_lstm_raw` (scaler) y `feature_columns_hybrid` (XGB).

## `tls.py` — `TlsClassifier`

- XGBoost entrenado sobre `build_network_features` (sin LSTM).
- Valida `feature_columns_tls`.

## `anomaly.py` — `AnomalyClassifier`

- LSTM Autoencoder; traduce el MSE contra `threshold` a `'ataque'`/`'normal'`.
- Constantes: `LABEL_NORMAL = 'normal'`, `LABEL_ANOMALY = 'ataque'`.
- Valida `feature_columns_lstm_raw` (scaler).

## `xgb.py` — `XgbClassifier`

- XGBoost binario sobre el set MQTT compacto (`build_case1`).
- Valida `feature_columns_case1`.

## `__init__.py`

Reexporta `AnomalyClassifier`, `HybridClassifier`, `TlsClassifier` y
`XgbClassifier`.
