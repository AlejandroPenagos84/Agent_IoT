# tshark adapters

`stream_features.py` is the capture sidecar. It runs tshark, coerces selected
fields, and appends one JSON record per frame.

`tshark_feature_source.py` implements the application `FeatureSource` port. It
tails that JSONL file, handles partial lines, and converts records into domain
context plus model features.

`tshark_schema.py` defines the canonical network column order shared by capture,
frame conversion, and classifiers.

`Dockerfile.capture` empaqueta únicamente los módulos del recolector y su
schema, además de los `__init__.py`. No necesita `application`, `domain` ni
dependencias ML. El paquete carga `TsharkFeatureSource` de forma lazy solo
cuando se importa explícitamente, para que arrancar el recolector con `python
-m infrastructure.tshark.stream_features` no cargue el agente.

Para aplicar cambios del sidecar: `podman-compose up -d --build
--force-recreate capture`. Por defecto captura todas las tramas; `--filter`
permite restringirlas. Los campos del CSV no disponibles en tshark quedan
como `null` con un aviso.

La captura incluye `ip.dst` y `tcp.stream` como contexto de conexión, sin
añadirlos a las features del modelo. El agente mantiene buffers por conexión y
dirección: `(tcp.stream, ip.src, tcp.srcport, ip.dst, tcp.dstport)`. Así no mezcla
respuestas del broker a distintos clientes ni conexiones que reutilizan puertos
en una misma captura. Cada dirección mantiene su propia ventana.

En modo por conexión se omiten registros sin IP/puerto de origen o destino;
`tcp.stream` es opcional para fuentes que no lo proporcionan. Las capturas
antiguas sin `ip.dst` no sirven en este modo. Reconstruir y recrear `capture` y
`agente` para activar el nuevo contexto; no hace falta borrar el JSONL.

`FrameContext` correlaciona identidad y topic por `tcp.stream`: al observar un
CONNECT guarda `mqtt.clientid`, y recuerda el último `mqtt.topic` visto. Los
frames siguientes del mismo flujo heredan ambos, de modo que la alerta no queda
con `client_id`/`topic` nulos cuando el frame final no los trae. Sin `tcp.stream`
no hay estado. El estado se reinicia en `start()` y si el JSONL se trunca.
