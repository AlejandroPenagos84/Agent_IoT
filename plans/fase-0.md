# Fase 0 — Conservar diagnóstico y admisión de L2

Leer primero [README.md](README.md). Esta fase no requiere ejecutar nada.

## Estado de partida

`reports/fase0.md` y `reports/fase0-opcion-a.md` documentan diagnóstico y ampliación
a TCP+L2. `load_and_merge` del notebook ya admite frames sin TCP completo si tienen
MAC origen/destino y tiempo válido. La captura incluye MAC y usa filtro base vacío.
La opción A ya forma parte del código; no pedir al usuario elegirla otra vez.

Considerar esta fase existente, con revisión estática del contrato. No reproducir
su entrenamiento ni borrar el historial. Las métricas antiguas son binarias.

## Archivos que leer

- `ml-mqtt-model.ipynb`: carga, `_observation`, `_connection`, `_direction` y split.
- `infrastructure/tshark/{stream_features,tshark_schema,tshark_feature_source}.py`.
- `application/use_cases/agent.py`, `domain/model.py`, `docker-compose.yml`.
- Los dos reportes mencionados. Algunas rutas antiguas de documentación ya no
  corresponden: la captura vigente está en `infrastructure/tshark/`.

## Contrato que conservar y completar si falta

1. TCP observable: timestamp finito, IP origen/destino no vacías y puertos enteros
   entre 1 y 65535. No completar puertos faltantes para convertir un frame en TCP.
2. Si no cumple TCP: admitir como `l2` cuando tiene timestamp finito y ambas MAC
   no vacías. Normalizar MAC con `strip().lower()` en los dos recorridos.
3. Si no cumple ninguna condición: registrar descarte con causa. No inventar contexto.
   La categoría `l2` puede incluir protocolos no TCP con IP; no equivale a «ARP».
4. Episodio L2: par MAC no dirigido; nuevo episodio por gap **estrictamente > 1 s**
   o retroceso de reloj. Ventana por dirección `eth.src → eth.dst` dentro del episodio.
5. Definir segmentos por retroceso temporal en el orden original de cada captura
   antes de cualquier ordenamiento que pueda ocultarlo. Orden estable por tiempo
   dentro del segmento. Reiniciar estados al cambiar captura/segmento.
6. Conservar identidad de fila `(captura, fila original)` antes de filtrar. Mantenerla
   en diagnósticos y manifiestos; nunca usarla como feature.
7. La exclusión del topic de alertas no debe excluir frames por ausencia de MQTT.
   Escribir su comprobación en las pruebas finales, sin iniciar tshark ahora.

## Diagnósticos que deberá producir la ejecución final

Por captura, clase y partición: filas originales, aceptadas TCP, aceptadas L2,
descartadas por causa, grupos independientes y filas que terminan ventana completa.
Contar faltantes de IP/puertos sin usarlos como motivo automático para perder L2.
Separar conteos de causas superpuestas del número total de frames descartados.

Conservar los diagnósticos de `hdrflags`, `mqtt.len`, representación de `mqtt.msg`,
columnas constantes y duplicadas. Prepararlos como funciones para la fase 5 si faltan.
No ejecutar su cálculo durante la implementación.

## Cierre de código

- [ ] Los contratos están implementados o se identificó su tarea concreta en fase 3.
- [ ] Hay comprobaciones escritas para TCP, L2, ausencia de contexto y límites del gap.
- [ ] No se eliminan frames L2 por exigir MQTT/IP/TCP.
- [ ] No se afirma que admitir L2 equivale a detectar correctamente MitM.
- [ ] Ninguna ejecución, cambio de artefactos o nueva métrica en esta fase.
