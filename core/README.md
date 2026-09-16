# `core/` — Contracts & Shared Types

Núcleo de **contratos** del sistema. No contiene lógica de modelos, ni red, ni broker.
Aplica el patrón **Ports & Adapters (Hexagonal)**: aquí viven los *ports* (interfaces
`Protocol`) y los *types* compartidos; los *adapters* viven en las demás carpetas
(`sources/`, `classifiers/`, `metadata/`, `rules/`, `sinks/`).

Regla de dependencia: **todos dependen de `core`; `core` no depende de nadie.**

## `types.py`

Tipos de datos compartidos entre adaptadores. Sin comportamiento salvo serialización.

| Símbolo | Tipo | Rol |
|---|---|---|
| `FEATURE_COLUMNS` | `tuple[str, ...]` | Orden canónico de las **7 features de red** que consumen los modelos. Fuente única de verdad del *schema*. |
| `FeatureRow` | `dict[str, float]` | Una fila de features (clave = columna, valor = float). |
| `ALERT_KIND_CLASS` | `str` (`'class'`) | Tipo de alerta por **clasificación** multiclase. |
| `ALERT_KIND_ANOMALY` | `str` (`'anomaly'`) | Tipo de alerta por **anomalía** binaria (LSTM). |
| `ALERT_KIND_INTRUSION` | `str` (`'intrusion'`) | Tipo de alerta por **regla** del broker. |
| `ClientMeta` | `@dataclass(frozen, slots)` | Identidad estable de un cliente: `client_id`, `ip`, `srcport`, `dstport`. |
| `ConnectionEvent` | `@dataclass(frozen, slots)` | Evento de conexión observado en el broker: `ts`, `client_id`, `ip`, `srcport`, `dstport`, `username`, `anonymous`. |
| `Alert` | `@dataclass(frozen, slots)` | Resultado normalizado del sistema. Campos: `ts`, `kind`, `label`, `client_id`, `ip`, `topic`, `mse`, `source`. Método `to_dict()` → `dict` serializable a JSON. |

`ClientMeta`, `ConnectionEvent` y `Alert` son `frozen` + `slots`: inmutables y ligeros
(se crean en bucle caliente).

## `protocols.py`

*Ports* definidos con `typing.Protocol` (**structural typing**). No hay herencia:
cualquier clase que implemente los métodos cumple el contrato (`isinstance` funciona
con `@runtime_checkable`). Esto habilita **Dependency Inversion**: el orquestador
`Agent` depende de estas abstracciones, no de implementaciones concretas.

| `Protocol` | Métodos | Implementado por |
|---|---|---|
| `Clock` | `now() -> float` | `core.clock.SystemClock`, `MonotonicClock` |
| `MetadataProvider` | `get(client_id) -> ClientMeta \| None`, `events() -> Iterator[ConnectionEvent]` | `metadata.BrokerLogRegistry` |
| `FeatureSource` | `start() -> None`, `rows() -> Iterator[FeatureRow]` | `sources.PlaintextMqttSource`, `TlsMqttSource` |
| `Classifier` | `predict(window) -> list[str]` | `classifiers.*Classifier` |
| `AlertSink` | `emit(alert) -> None` | `sinks.*Sink` |
| `IntrusionRule` | `check(event) -> Alert \| None` | `rules.AnonymousConnectRule`, `ConnectionChurnRule`, `AnyRule` |

## `clock.py`

Adaptadores de tiempo inyectables (facilitan tests deterministas).

- **`SystemClock`** — `now()` vía `time.time()` (epoch absoluto). Se usa en el agente
  para que los `ts` de frames y eventos sean comparables con el log del broker.
- **`MonotonicClock`** — `now()` vía `time.monotonic()`. Adecuado para medir intervalos
  donde no importa la hora de pared.

## `__init__.py`

Reexporta tipos, constantes, protocolos y relojes para que el resto del código importe
todo desde `core` (`from core import FeatureRow, Classifier, SystemClock`).
