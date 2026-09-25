# Fase 2 — Refinar novedad de origen

Leer primero [README.md](README.md). Escribir cambios y pruebas; no ejecutarlos.

## Estado y problema

`fe_origen_conocido`, `known_origins` y sus loaders ya existen. El lookup actual usa
IP o client ID del frame. `reports/fase2.md` registra que los 380 frames de Intrusion
del test histórico tenían origen conocido: esta feature no equivale a «Intrusion».
Actualmente el valor 0 también puede representar falta completa de identidad.

## Archivos

- Notebook: construcción post-split de `known_origins` y `fe_origen_conocido`.
- `infrastructure/classifiers/_common.py`: lookup y carga de artefactos.
- `infrastructure/tshark/tshark_feature_source.py`, `tshark_schema.py`.
- `tests/test_mqtt_features.py`, `tests/validate_notebook.py`.

## Implementación exacta

1. Mantener claves `ip:<valor>` y `client:<valor>`, quitando espacios y valores vacíos.
   No cambiar mayúsculas del client ID. No usar MAC como sustituto de IP/client ID.
2. Aprender el conjunto solo de frames `normal` del train de ese ajuste. Congelarlo
   al transformar validation/test y durante inferencia. No aprendizaje online automático.
3. Mantener lookup sobre client ID **presente en el frame** en ambos recorridos.
   El client ID correlacionado para metadatos de alerta no se convierte silenciosamente
   en entrada de la feature. Propagar identidad sería otro experimento, fuera de esta fase.
4. Conservar `fe_origen_conocido`: 1 si cualquiera de las claves disponibles está
   en el conjunto; 0 en los demás casos. Añadir `fe_origen_observable`: 1 si existe
   al menos una clave válida; 0 si faltan ambas. Así `(0,0)` significa no observable
   y `(0,1)` origen observado pero desconocido. No asignar una clase mediante reglas.
5. Actualizar listas de features y **generador** de `pipeline_config.json` con ambos
   campos, etapas y reglas. No modificar `modelos_agente/known_origins.json` ni su config.
6. Mantener errores explícitos al faltar el artefacto requerido. No sustituirlo por
   un conjunto vacío para hacer compatibles modelos viejos.

## Evaluación que preparar para el final

Preparar comparación multiclase con/sin las dos features de origen como un bloque,
con igual población, particiones y semillas. Registrar por clase/observación los
casos conocidos, desconocidos y no observables. Selección exclusivamente con validation.
No ejecutar ablation ahora ni afirmar que mejorará Intrusion.

## Pruebas que dejar escritas

- IP conocida, client ID conocido, ambas claves desconocidas y ambas ausentes.
- IP conocida más client ID desconocido conserva resultado 1 por la regla OR.
- Claves vacías, espacios y prefijos distintos.
- Identidad exclusiva de validation/test no entra en el conjunto.
- Mismos registros dan iguales features offline/online, incluyendo frames L2.
- Metadatos correlacionados de alertas no modifican el lookup del frame.

## Cierre de código

- [ ] Ausencia de identidad y origen desconocido son distinguibles.
- [ ] Construcción y consumo comparten contrato y orden de columnas.
- [ ] La ablation está preparada, sin resultados inventados.
- [ ] Pruebas escritas; ejecución y exportación pendientes del usuario.
