# MQTT/IoT simulation

The simulator publishes real normal and attack traffic to Mosquitto. Capture,
feature extraction, and detection remain outside this package.

```bash
python -m simulation --broker localhost --port 1883 --paquetes 500 --ataque todos --verbose
python -m simulation --dry-run --ataque todos --force-attack
```

## Ritmo y escenarios

`--ataque todos` recorre `dos → mitm → intrusion` y repite el ciclo. Reserva
presupuesto para una ráfaga completa de cada tipo; exige
`--paquetes >= 3 * --burst-size + 2` (dos publicaciones normales para discovery).
`--paquetes` cuenta publicaciones MQTT,
no frames TCP ni alertas. El tráfico normal comparte ese presupuesto.

```bash
python -m simulation --broker localhost --ataque todos --paquetes 500 \
  --burst-size 100 --dos-rate 100 --attack-rate 10 --attack-gap 5 \
  --force-attack --seed 42 --verbose
```

El horario usa `time.monotonic()` y las ráfagas esperan deadlines reales;
`--intervalo` es la pausa del scheduler, no un multiplicador del reloj.
`--dos-rate` y `--attack-rate` son publicaciones por segundo; cada ráfaga
imprime su duración y ritmo observado de envío. La conexión se establece antes
de medir la ráfaga. Los retrasos del sistema pueden reducir el ritmo real.
El tráfico normal se pausa durante las ráfagas. `--dry-run` usa tiempo virtual,
sin esperas ni conexión, y no mide rendimiento de red.

Los escenarios generan tráfico real inspirado en MQTT_UAD, sin reproducir
exactamente las capturas históricas. Los dispositivos publican lecturas
numéricas a `distance/ultrasonic1` y valores `0`/`1` a `light/rele1`, topics
presentes en los CSV locales.

- `dos`: publicaciones multicliente en `mqtt-malaria/.../data/...`, con payload
  hexadecimal de longitud configurable. `--dos-clients` (5 por defecto),
  `--dos-payload-size` (100 por defecto) y `--dos-rate` controlan la carga.
  Generar carga no demuestra denegación de servicio.
- `mitm`: el sensor `sonar_mitm` publica `100` a `distance/ultrasonic1` a través
  de un proxy TCP local que modifica el PUBLISH en tránsito a `900`, conservando
  longitud y framing. El sensor se conecta explícitamente al proxy; no se
  realiza el ARP spoofing de Ettercap empleado en el dataset. Se usa QoS 1 para
  esperar PUBACK del broker, a diferencia de los ejemplos QoS 0 de los CSV.
- `intrusion`: un cliente anónimo se suscribe a `#`, recibe publicaciones de
  los dispositivos y publica datos falsos en los topics realmente observados.
  `--discovery-seconds` controla la espera inicial (2 segundos por defecto).
  En `--dry-run` se usan los topics previstos de los dispositivos, sin afirmar
  que se hayan observado en una red. El acceso depende de la configuración
  del broker; una conexión o suscripción rechazada detiene la ejecución.

Las etiquetas del escenario no son ground truth de frames ni etiquetas ML.
El simulador no inventa features ni etiquetas de captura; tshark extrae los
campos del wire. Los modelos MQTT ahora pueden derivar features de aplicación,
pero reproducir un escenario no garantiza que el modelo lo clasifique igual:
ritmos, clientes, topología y distribución de mensajes pueden ser diferentes.

El publisher espera CONNACK, comprueba el código de retorno de cada publicación
y drena los envíos pendientes antes de desconectar. Un fallo produce un error
en vez de anunciar una ejecución completada. Con QoS 0, completar un envío no
confirma aceptación por ACL ni entrega al consumidor; para eso se necesita
verificación adicional del broker/consumidor.

Pruebas: `python -m unittest discover -s tests -v`.

`simulador_iot.py` remains a backward-compatible wrapper. Dockerfile and Compose
run `python -m simulation` directly.

| Module | Responsibility |
|---|---|
| `devices.py` | Device definitions, normal topics, payloads, and intervals. |
| `publishers.py` | `Publisher` port plus MQTT and no-op implementations. `paho` is imported lazily. |
| `attacks.py` | Immutable attack packet descriptions and scenario builders. |
| `mqtt_proxy.py` | Transformador de PUBLISH, handler, servidor TCP y proxy; clases definidas al nivel del módulo. |
| `simulator.py` | Scheduling, publisher caching, bursts, logging, and shutdown. |
| `cli.py` | Command-line parsing and process entry point. |
| `__main__.py` | Enables `python -m simulation`. |

TLS is enabled with `--tls` or port `8883`; los escenarios `mitm` y `todos`
requieren MQTT sin TLS. `--dry-run` never connects. Supported
scenarios are `none`, `dos`, `mitm`, `intrusion`, and `todos`. The simulator
produces traffic patterns; the classifier determines the final label.
