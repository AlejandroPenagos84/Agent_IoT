# Classifiers

These adapters implement the application `Classifier` port:
`predict(window: Sequence[FeatureRow]) -> list[str]`.
The only active adapter is `TcpXgbClassifier` (modelo final B).

`predict` returns one label per evaluable frame. The agent uses window size 1
for the TCP model: the capture sidecar already computes causal per-frame TCP
features, so the model scores each row independently.

Heavy imports (`xgboost`, `joblib`) are lazy, so merely importing this package
does not require loading the model.

## `TcpXgbClassifier` (modelo final B, solo TCP)

Carga `modelos_agente_tcp/` (`03_modelo_tcp.ipynb`): `xgb_tcp.ubj`,
`le_target.joblib` y `pipeline_config.json` (`feature_mode='tcp'`). Valida que el
booster exponga exactamente `feature_columns_tcp`. No calcula features: el sidecar
ya envía las 12 features TCP causales de cada frame en `tcp_features`, y el
worker del broker las entrega tal cual, omitiendo los registros sin ellas
(frames sin puerto 1883/8883). Puntúa cada fila de forma independiente con
`inplace_predict` en un hilo (~0,4 ms/frame); umbral 0,5.

`build_agent` usa ventana 1, `server_ports=(1883, 8883)` (la alerta reporta la IP
del cliente aunque el frame sea respuesta del broker) y un cooldown de 5 s por
conexión: como mucho una alerta durante el handshake, sin `client_id`, y otra
cuando se conoce el CONNECT. En Compose es el único modelo.

Limitación: `tcp_new_conns_5s` cuenta conexiones nuevas en toda la red. Durante un
flood, algunos frames de dispositivos normales también se marcan como ataque. En la
prueba con el simulador, `relay` y `sonar` generaron 3 alertas cada uno durante el
ataque y ninguna con solo tráfico normal.

## Helpers

`_common.load_config` lee `pipeline_config.json` y `validate_named_features`
comprueba que el modelo exportado exponga las mismas features en el mismo orden.
