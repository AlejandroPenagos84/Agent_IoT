# Plan: comparar features MQTT (A) contra solo TCP (B)

## Objetivo

Decidir si el modelo DoS usa campos de la capa MQTT (solo existen en MQTT en
claro) o solo features TCP/IP (también existen con MQTTS). La única forma de
decidirlo es comparar ambos sets con los mismos datos, la misma división y el
mismo modelo. Este plan no cambia las celdas de los modelos, el agente ni
`modelos_agente/`.

## Paso 1: concurrencia temporal en `DoS.csv`

Nueva celda **2.3.4**, con el código directo en la celda:

- Etiqueta contra `frame.time_epoch`, en dos vistas: puntos por frame y frames
  por segundo apilados por clase.
- Las dos vistas otra vez, solo con frames del puerto 1883/8883.
- Tabla con la ventana del ataque `[primer DoS, último DoS]` y los frames
  normales antes, durante y después, en total y solo MQTT.

Decisión:

- **Hay normal concurrente** (≥ 20% del normal MQTT de `DoS.csv` cae dentro de
  la ventana del ataque): se mantiene la división agrupada por conexión.
- **No hay normal concurrente**: además de esa división, se evalúa con
  *leave-one-capture-out* del normal (entrenar con el normal de dos capturas,
  probar con el de la tercera). Así se mide si el modelo reconoce "normal" o
  reconoce "antes/después del ataque".

## Paso 2: alcance

- **Frames**: IPv4/TCP con puerto 1883 u 8883 en origen o destino. Se filtra por
  puerto, no por capa MQTT. Así se conservan los SYN/ACK de las conexiones
  MQTT, que el agente también ve, y el 14% de frames DoS sin capa MQTT.
- **Datos**: `DoS.csv` completo más el normal de `MitM.csv` e `Intrusion.csv`.
- **Separación del EDA**: se aplica después del EDA (sección 2.8) sobre una
  variable nueva `df_scope`. `df_raw`, que alimenta los modelos, no cambia
  hasta decidir.
- **Comprobación**: los 5 folds tienen conexiones normales de las tres capturas.
  Si no, se reduce el número de folds y se documenta.

## Paso 3: los dos sets de features

**A: actual (13 features, MQTT en claro).** `FEATURE_COLUMNS` sin cambios.

**B: solo TCP (observable con MQTTS).** Todas las features se calculan de forma
causal (solo frames anteriores, como el agente en tiempo real). La clave es
`_direction`; las ventanas son de 5 s y excluyen el frame actual. Sin historial,
el valor es 0.

| feature | definición |
|---|---|
| `frame.len`, `fe_log_len` | tamaño del frame y `log1p` |
| `frame.time_delta` | tiempo desde el frame anterior de la captura |
| `fe_is_standard_mqtt_port`, `fe_is_broker_to_client` | dirección respecto al broker |
| `tcp_iat` | tiempo desde el frame anterior de la misma dirección |
| `tcp_iat_std_5s` | desviación del inter-arrival en la ventana (ráfagas regulares) |
| `tcp_frames_5s`, `tcp_bytes_5s` | frames y `log1p(bytes)` de la dirección en la ventana |
| `tcp_len_std_5s` | dispersión de tamaños en la ventana |
| `tcp_asymmetry_5s` | frames cliente→broker / frames totales de la conexión en la ventana |
| `tcp_new_conns_5s` | pares de endpoints nuevos hacia el broker en la ventana (sustituto TCP del conteo de CONNECT) |

El CSV no trae `tcp.flags`, `tcp.len` ni `tcp.window_size`, así que B no puede
usarlos. Las features de B van en `data_preprocessing/tcp_features.py` para
replicarlas luego en el agente. IP, puertos crudos y `time_epoch` solo se usan
como claves de agrupación y orden, nunca como features.

## Paso 4: comparación

Nueva sección **2.9**, sobre `df_scope`:

- **Modelo**: un XGBoost con los mismos hiperparámetros fijos para A y B, sin
  Optuna, con `sample_weight` balanceado.
- **División**: 5-fold `StratifiedGroupKFold` por `_connection`, más
  leave-one-capture-out si el paso 1 lo exige.
- **Línea base**: la mejor regla trivial dentro del alcance (por ejemplo
  "cliente → broker ⇒ DoS"). Un set que no la supere no aporta nada.
- **Métricas**: macro-F1, balanced accuracy, ROC-AUC y recall de DoS, como
  media ± std por fold. Además, la tasa de falsos positivos por captura de
  origen del normal (DoS, MitM, Intrusion).
- **Importancia**: la de las features de cada set, para detectar si una sola
  domina.
- **Sensibilidad a TLS (aproximada, opcional)**: sumar entre 21 y 40 bytes a
  `frame.len` de los frames MQTT de test y medir la caída de B. No sustituye a
  una validación real con MQTTS.

## Paso 5: decisión

Criterio propuesto, a confirmar:

- **B**: si su macro-F1 queda a ≤ 0.03 de A, supera la línea base y no
  aumenta los falsos positivos en ninguna captura de origen.
- **A**: si B pierde más de eso. En ese caso se documenta que el modelo solo
  vale para MQTT en claro.

Si se elige B, pasos posteriores fuera de este plan:

1. Política de columnas: las `mqtt.*` del modelo pasan a DROP con un motivo
   nuevo, `NOT_OBSERVABLE_TLS`.
2. Cambiar `FEATURE_COLUMNS`, `infrastructure/classifiers/_common.py` y
   `pipeline_config.json`.
3. Reentrenar y reexportar `modelos_agente/`.
4. Validar con una captura propia del simulador sobre 8883.

## Fuera de alcance

Optuna, LSTM, híbrido, exportación, cambios en el agente y en el compose.

## Riesgos

- **Desplazamiento con TLS**: el dataset es MQTT en claro. Con TLS los frames
  crecen y aparece el handshake; ese desplazamiento no se puede medir con estos
  datos.
- **Poco normal de `DoS.csv` en el alcance** (~969 frames): sus métricas por
  captura tendrán alta varianza.
- **Un solo ataque DoS grabado**: B y A pueden estar aprendiendo la
  herramienta concreta, no DoS en general.
