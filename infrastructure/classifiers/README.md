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

## `TcpXgbClassifier` (modelo final B, solo TCP) — `model='tcp'`

Carga `modelos_agente_tcp/` (`03_modelo_tcp.ipynb`): `xgb_tcp.ubj`,
`le_target.joblib` y `pipeline_config.json` (`feature_mode='tcp'`). Valida que el
booster exponga exactamente `feature_columns_tcp`. No calcula features: el sidecar ya
escribe las 12 features TCP causales de cada frame en `tcp_features`, y
`TsharkFeatureSource(feature_key='tcp_features')` las entrega tal cual, omitiendo los
frames con `null` (sin puerto 1883/8883). Puntúa cada fila de forma independiente con
`inplace_predict` en un hilo (~0,4 ms/frame); umbral 0,5.

`build_agent` con `model='tcp'` usa ventana 1, `server_ports=(1883, 8883)` (la alerta
reporta la IP del cliente aunque el frame sea respuesta del broker) y un cooldown de
5 s por conexión: como mucho una alerta durante el handshake, sin `client_id`, y otra
cuando se conoce el CONNECT. En Compose es el modelo por defecto (`MODELO=tcp`).

Limitación: `tcp_new_conns_5s` cuenta conexiones nuevas en toda la red. Durante un
flood, algunos frames de dispositivos normales también se marcan como ataque. En la
prueba con el simulador, `relay` y `sonar` generaron 3 alertas cada uno durante el
ataque y ninguna con solo tráfico normal.

## Contrato de features (MQTT en claro)

`_common.build_mqtt_features` es el espejo de `build_mqtt_features` de
`ml-mqtt-model.ipynb`: 13 features compactas, **sin `tcp.srcport`/`tcp.dstport`
crudos** y sin columnas de identidad, reloj de captura ni duplicados.

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
  con las 7 columnas de `infrastructure/tshark/tshark_schema.py`.

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
