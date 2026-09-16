# Detección de intrusiones en tráfico IoT/MQTT

Sistema de detección de ataques (DoS, MitM, Intrusion) sobre tráfico MQTT/IoT en tiempo
real. Un **simulador** publica tráfico real en un **broker Mosquitto**; un **agente**
suscrito al broker clasifica los frames con modelos de Machine Learning y publica
**alertas**. El diseño asume que el tráfico puede ir **cifrado (MQTTS)**, por lo que la
decisión usa solo features de red/transporte.

> **Bilingüe / Bilingual:** la prosa va en español; los términos técnicos
> (`Protocol`, `FeatureSource`, `Composition Root`, `Adapter`, etc.) se mantienen en inglés.

---

## 1. Arquitectura general

```text
                        ┌── listener 1883 (plaintext) ──┐
 [simulador_iot.py] ───▶│                               │◀─── [agente_mqtt.py]
   paho publish         └── listener 8883 (TLS/MQTTS) ──┘        │
                    [mosquitto]                                  │ publish
                        │  escribe log                           ▼
                        └──────────▶ [BrokerLogRegistry]   alertas/deteccion
                                          (ip/puerto,            │
                                           CONNECT anón.)       ▼
                                                        [LLM reportes] (futuro)
```

Flujo de datos dentro del agente:

```text
FeatureSource.rows() ──▶ FeatureRow (7 features) ──▶ buffer (ventana 11)
                                                          │
                                                          ▼
                                              Classifier.predict(window)
                                                          │
                                     label != 'normal' ──▶ AlertSink.emit()

MetadataProvider.events() ──▶ ConnectionEvent ──▶ IntrusionRule.check()
                                                          │
                                                     Alert ──▶ AlertSink.emit()
```

## 2. Patrón de diseño

El proyecto aplica **Ports & Adapters (Hexagonal)** con **Dependency Inversion**:

- **Ports** (contratos) viven en `core/protocols.py` como `Protocol` (structural typing).
  No hay superclases ni herencia.
- **Adapters** concretos viven en `sources/`, `classifiers/`, `metadata/`, `rules/` y
  `sinks/`. Cada clase implementa un port de forma independiente.
- **Composition Root**: `factory.py` construye los adaptadores según `AgentConfig` y los
  inyecta en `Agent`. Añadir un caso nuevo (p. ej. un `TsharkSource`) o un modelo
  distinto = nueva clase + una línea en el factory, sin tocar el orquestador.
- **Strategy** en sources/classifiers/sinks (intercambiables por configuración),
  **Composite** en `AnyRule` y `CompositeAlertSink`, **Adapter** en los clasificadores
  (envuelven `MQTTDetector`).

Regla de dependencia: **todos dependen de `core`; `core` no depende de nadie.**

## 3. Mapa del repositorio

| Ruta | Rol | Doc detallada |
|---|---|---|
| `core/` | Contratos (`Protocol`) y tipos compartidos. | [`core/README.md`](core/README.md) |
| `sources/` | Convierten mensajes MQTT en `FeatureRow` (plaintext / TLS). | [`sources/README.md`](sources/README.md) |
| `classifiers/` | Adaptadores que envuelven `MQTTDetector` para clasificar. | [`classifiers/README.md`](classifiers/README.md) |
| `metadata/` | Identidad de clientes y topics a partir del log del broker. | [`metadata/README.md`](metadata/README.md) |
| `rules/` | Reglas deterministas de intrusión (CONNECT anónimo, churn). | [`rules/README.md`](rules/README.md) |
| `sinks/` | Destinos de alertas (MQTT, archivo, composite). | [`sinks/README.md`](sinks/README.md) |
| `mosquitto/` | Configuración del broker + generación de certificados. | [`mosquitto/README.md`](mosquitto/README.md) |
| `modelos_agente/` | Artefactos de ML exportados por el notebook. | sección 6 |

### Módulos raíz (overview)

- **`agent.py`** — `Agent`: el orquestador. Depende **solo** de los ports. Un hilo
  consume `MetadataProvider.events()` y aplica `IntrusionRule`; el hilo principal
  mantiene la ventana de `FeatureRow`, llama a `Classifier.predict` y emite la última
  etiqueta no normal al `AlertSink` (con `alert_cooldown` por etiqueta).
- **`factory.py`** — `AgentConfig` (dataclass) + `build_source` / `build_sink` /
  `build_agent`. Es el **Composition Root**: lee la config y construye los adaptadores.
- **`agente_mqtt.py`** — CLI del agente. `parse_args` → `AgentConfig`, `main` →
  `build_agent(...).run()`.
- **`simulador_iot.py`** — Simulador MQTT real. `IoTDevice` (dispositivo virtual),
  `build_devices()`, `MqttPublisher` / `DryPublisher`, `Simulator` (bucle normal +
  ráfagas de ataque). Publica en paho; **no** detecta.
- **`agent_inference.py`** — `MQTTDetector`: carga los modelos y reproduce el
  preprocesado del notebook. Métodos: `predecir_caso1`, `predecir_tls`,
  `predecir_anomalia`, `predecir_hibrido`. Incluye un CLI mínimo que imprime la
  predicción híbrida de un CSV.
- **`mqtt_utils.py`** — `make_client(...)`: crea un cliente paho compatible con 1.x y 2.x
  (maneja `CallbackAPIVersion`). Usado por `sources/_stream.py` y `sinks/mqtt_alert.py`.
- **`ml-mqtt-model.ipynb`** — Notebook de entrenamiento y exportación de los modelos.
- **`Dockerfile`** / **`docker-compose.yml`** — Imagen única `proyecto:latest`; cómo se
  orquesta `certgen` + `mosquitto` + `agente` + `simulador`.

## 4. Quickstart con contenedores (recomendado)

```bash
docker compose up --build       # o: podman-compose up --build
```

Esto levanta:

1. `certgen` — genera CA y certificado TLS autofirmado y prepara el log.
2. `mosquitto` — listeners `1883` (claro) y `8883` (TLS); log a volumen compartido.
3. `agente` — modelo `hybrid`, lee el log del broker, publica en `alertas/deteccion`.
4. `simulador` — publica tráfico normal + ataques (`--ataque todos`).

Para ver las alertas:

```bash
podman exec -it mosquitto mosquitto_sub -t 'alertas/#' -v
```

Opcional (fase 2): un sidecar `tshark` para features exactas de red sobre el broker.

## 5. Quickstart local (sin contenedores)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Ejecutar el simulador contra un broker existente:

```bash
python simulador_iot.py --broker localhost --port 1883 \
  --paquetes 100 --ataque todos --verbose
```

Ejecutar el agente:

```bash
python agente_mqtt.py --source plaintext --model hybrid \
  --modelos modelos_agente --broker localhost \
  --log /var/log/mosquitto/mosquitto.log \
  --alert-topic alertas/deteccion --alert-file alerts.jsonl
```

Inferencia sobre un CSV (sin broker; imprime la predicción híbrida por frame):

```bash
python agent_inference.py modelos_agente nuevo_trafico.csv
python agent_inference.py modelos_agente nuevo_trafico.csv --device cpu
```

### Flags del simulador

| Flag | Default | Descripción |
|---|---|---|
| `--broker` / `--port` | `localhost` / `1883` | Destino MQTT. |
| `--tls` / `--ca-certs` | off / `/mosquitto/certs/ca.crt` | Conectar por TLS. |
| `--paquetes` | `60` | Nº total de mensajes a publicar. |
| `--ataque` | `none` | `none`, `dos`, `mitm`, `intrusion` o `todos`. |
| `--intervalo` | `0.5` | Pausa entre iteraciones (s). |
| `--usuario` / `--usuario-ataque` | `iot` / `atacante` | Usernames (la intrusión conecta **anónimo**). |
| `--force-attack` | off | Primer ataque inmediato. |
| `--verbose` / `--debug` | off | Log por paquete / planificación. |
| `--dry-run` | off | No conecta; solo imprime lo que publicaría. |

### Flags del agente

| Flag | Default | Descripción |
|---|---|---|
| `--source` | `plaintext` | `plaintext` (1883) o `tls` (8883). |
| `--model` | `hybrid` | `hybrid`, `tls`, `case1` o `anomaly`. |
| `--modelos` | `/app/modelos_agente` | Directorio de artefactos. |
| `--broker` / `--port` | `localhost` / auto | Broker (puerto por defecto según `--source`). |
| `--log` | `None` | Ruta del log de Mosquitto (activa el `MetadataProvider`). |
| `--topics` | `home/# admin/# cmd/#` | Filtros de suscripción. |
| `--ventana` / `--cooldown` | `11` / `2.0` | Tamaño de ventana y cooldown de alertas. |
| `--alert-topic` / `--alert-port` | `alertas/deteccion` / `1883` | Destino de alertas MQTT. |
| `--alert-file` | `None` | Añade un `FileAlertSink`. |
| `--sin-reglas` | off | Desactiva las reglas de intrusión. |
| `--ca-certs` / `--insecure` | — | TLS del suscriptor. |

## 6. Modelos y datos

Los artefactos de `modelos_agente/` los produce `ml-mqtt-model.ipynb` (dataset
**MQTTset**). No son código fuente y no se editan a mano.

| Archivo | Contenido |
|---|---|
| `pipeline_config.json` | Contrato del pipeline: `seq_len=10`, umbral LSTM, clases y orden exacto de columnas por modelo. |
| `xgb_case1.ubj` | XGBoost multiclase (todas las features). |
| `xgb_tls.ubj` | XGBoost multiclase con features de red/transporte. |
| `xgb_hybrid.ubj` | XGBoost con `fe_lstm_mse` (modelo por defecto). |
| `lstm_ae.pt` | LSTM Autoencoder en TorchScript portable. |
| `scaler.joblib` | `StandardScaler` para las secuencias del LSTM. |
| `le_target.joblib` | `LabelEncoder` de clases. |

Dos escenarios: **Caso 1** (dataset completo) y **Caso 2** (cifrado: solo cabeceras de
red). El agente usa el **híbrido** (XGBoost + MSE del LSTM), del Caso 2.

## 7. Convenciones

- **Topics**: normales en `home/...`; no autorizados en `admin/...`; de control en
  `cmd/...`; alertas del agente en `alertas/deteccion`.
- **Alertas**: JSON de `Alert.to_dict()` (`ts`, `kind`, `label`, `client_id`, `ip`,
  `topic`, `mse`, `source`).
- **Ventana**: el LSTM necesita `SEQ_LEN + 1 = 11` filas para producir una predicción.
- **Atribución**: MQTT no expone el `client_id` del publicador; se resuelve desde el log
  del broker (`owner(topic)`), con reintentos para cubrir la latencia del log.

## 8. Limitaciones

- El preprocesado debe respetar el orden/tipos de `pipeline_config.json`.
- Una categoría nueva para XGBoost puede fallar; normalizarla a `NOT_MQTT`.
- `BrokerLogRegistry` depende del formato exacto del log de Mosquitto.
- El timestamp del log es de resolución de segundo; el timing fino lo mide el agente.
- La inferencia real requiere `torch`/`xgboost` (el contenedor los instala). `torch`
  puede ser pesado: para build CPU usar la rueda CPU de PyTorch.
