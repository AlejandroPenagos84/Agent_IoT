# Plan — `01_eda_politica.ipynb`

## Objetivo

Concentrar en un solo notebook la carga, el EDA descriptivo, la política de
columnas y las decisiones sobre el dataset. Al final debe producir un artefacto
limpio y reproducible que consuman los otros dos notebooks.

Este notebook **no entrena modelos** ni compara A/B.

## Entradas

- `dataset/DoS.csv`
- `dataset/MitM.csv`
- `dataset/Intrusion.csv`
- `ML_Model/data_preprocessing/load_data.py`
- `ML_Model/data_preprocessing/column_policy.py`
- `ML_Model/data_preprocessing/eda/`

## Salidas

- `ML_Model/artifacts/df_raw.joblib` (DataFrame post-política).
- `ML_Model/artifacts/manifest.json` con:
  - capturas usadas y etiquetas conservadas;
  - conteos por captura y clase;
  - columnas finales;
  - hash del artefacto;
  - semilla y versión de features;
  - fecha de generación.

## Celdas de origen

Copiar las celdas **0–29** del notebook actual, en este orden:

| Celdas | Contenido |
|---|---|
| 0–5 | Título, imports, configuración y carga |
| 6–7 | 2.1 Nulos por columna |
| 8–9 | 2.2 Tipos de paquete MQTT por clase |
| 10–11 | 2.3 Rol del puerto MQTT por clase |
| 12–13 | 2.3.1 ¿MQTT = DoS? Verificación del proxy |
| 14–15 | 2.3.2 ¿Cambia la distribución al añadir normal de MitM/Intrusion? |
| 16–17 | 2.3.3 ¿El normal de las tres capturas es el mismo? |
| 18–19 | 2.3.4 Concurrencia temporal del normal en `DoS.csv` |
| 20–21 | 2.4 Duplicadas y redundantes |
| 22–25 | 2.5 `STRUCTURAL_NULL`: alineación y separación |
| 26–27 | 2.6 Tabla de política |
| 28–29 | 2.7 Aplicar la política y crear `df_raw` |

Después de la celda 29, añadir una celda nueva para guardar el artefacto y el
manifiesto.

## Contenido que debe conservar

- Carga de `DoS.csv` completo y solo el normal de `MitM.csv` e `Intrusion.csv`.
- Análisis de nulos, tipos de paquete, rol de puertos y proxy “MQTT = DoS”.
- Comparación del normal entre capturas.
- Concurrencia temporal: ventana `[primer DoS, último DoS]`, frames normales
  antes/durante/después, total y solo puerto 1883/8883.
- Decisión de 2.3.4: con 568/969 = 58,6 % de normal MQTT dentro de la ventana,
  se mantiene el split agrupado por conexión y no se exige LOCO.
- Duplicadas, redundantes, `STRUCTURAL_NULL` y política de columnas.
- Aplicación de la política y construcción de `df_raw`.
- Cierre con “Decisiones tomadas”:
  - etiquetas `normal`/`DoS`;
  - vistas `full` y `mqtt`;
  - columnas de contexto (`frame.time_epoch`, `_connection`, `_direction`,
    `_capture`);
  - motivo del descarte de identidad, puertos crudos y reloj;
  - sesgo de distribución que motiva usar TCP;
  - limitación de una sola captura DoS.

## Lo que no debe incluir

- Construcción de la matriz A o B.
- Comparación A/B/A'.
- Entrenamiento, Optuna, LSTM, híbrido o exportación.
- Celdas 30–64 del notebook actual.

## Artefacto limpio

La celda de guardado debe:

1. Validar que `df_raw` no está vacío y que `type` solo contiene
   `normal`/`DoS`.
2. Guardar con `joblib.dump(df_raw, 'ML_Model/artifacts/df_raw.joblib')`.
3. Escribir `manifest.json` con conteos, columnas, hash y metadatos.
4. Imprimir un resumen de clases por captura y conexiones por clase.

No se debe volver a limpiar el dataset: se asume que `load_data` y
`column_policy` ya son la limpieza oficial.

## Criterios de aceptación

- El notebook corre de arriba a abajo sin depender de celdas posteriores.
- `df_raw.joblib` se carga correctamente y conserva `_connection` y
  `_direction`.
- El manifiesto coincide con los conteos del notebook.
- No hay columnas de identidad, puertos crudos ni reloj dentro de las features
  del modelo; solo se conservan como contexto.
- Las decisiones quedan escritas en markdown al final, no solo en outputs.
