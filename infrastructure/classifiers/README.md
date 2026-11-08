# Classifiers

These adapters implement the application `Classifier` port:
`predict(window: Sequence[FeatureRow]) -> list[str]`.
They wrap the model artifacts exported by `ml-mqtt-model.ipynb` using the
Adapter and Strategy patterns.

`predict` returns one label per evaluable frame. The agent takes the last label,
corresponding to the newest frame in the window. With 11 rows and `SEQ_LEN=10`,
LSTM models evaluate two sequences and the last one ends at the frame used by
the alert.

Heavy imports (`torch`, `xgboost`, `joblib`, and `pandas`) are lazy, so merely
importing this package does not require loading the models.

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

`_common.build_mqtt_features` mirrors the notebook's feature builder. It
contains 13 compact features and excludes raw ports, identity columns, capture
clock values, and duplicate columns.

| Group | Columns |
|---|---|
| Network | `frame.len`, `frame.time_delta` |
| Derived network | `fe_bytes_per_sec`, `fe_is_standard_mqtt_port`, `fe_is_broker_to_client`, `fe_log_len` |
| MQTT | `mqtt.hdrflags`, `mqtt.len`, `mqtt.topic_len` |
| Derived MQTT | `fe_msg_entropy`, `fe_topic_entropy`, `fe_topic_depth`, `fe_payload_ratio` |

`modelos_agente/pipeline_config.json` defines the feature order. Each adapter
validates the configured order against the scaler and model before prediction.
The exported objective is binary: `normal` and `ataque`.

## Adapters

- `HybridClassifier`: compact MQTT features plus LSTM reconstruction error;
  this is the default when `composition_root` is used directly.
- `TlsClassifier`: XGBoost over network features.
- `AnomalyClassifier`: LSTM autoencoder; compares reconstruction error with
  the configured anomaly threshold.
- `XgbClassifier`: binary XGBoost over the compact MQTT feature set.

`load_config`, `select_features`, and `validate_named_features` provide model
configuration and validation. `build_network_features` and
`build_mqtt_features` construct the feature contracts, while sequence helpers
prepare LSTM input.
