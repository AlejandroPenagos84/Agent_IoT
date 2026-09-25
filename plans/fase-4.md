# Fase 4 — Cuatro clases y modelos temporales

Leer primero [README.md](README.md). Esta fase amplía la fase 4 histórica para
cumplir la petición de cuatro clases. Escribir código; el usuario entrenará al final.

## Arquitectura objetivo, sin alternativas implícitas

| Modo público | Modelo | Salida |
| --- | --- | --- |
| `xgboost` | XGBoost supervisado por frame | Cuatro clases |
| `lstm` | LSTM supervisado sobre secuencia, última fila como target | Cuatro clases |
| `hybrid` | XGBoost multiclase sobre features finales + MSE de autoencoder | Cuatro clases |
| Auxiliar, sin nuevo modo público | LSTM autoencoder entrenado con normal | Reconstrucción/MSE; referencia binaria opcional |

No convertir un único umbral de MSE en tres tipos de ataque. Conservar el autoencoder
para que el híbrido siga teniendo su feature `fe_lstm_mse` y para estudiar su regresión.

## 4.1 Targets, modelos y adapters

1. XGBoost e híbrido: `objective='multi:softprob'`, `num_class=4`, `mlogloss`, pesos
   según fase 1. Conservar los restantes hiperparámetros actuales salvo incompatibilidad.
2. LSTM supervisado: encoder con hidden size 32, último estado oculto → `Linear(32,4)`.
   `CrossEntropyLoss` con pesos de train; logits para la loss y softmax para probabilidades.
   Conservar de partida Adam 0.001, batch size 512 y 10 épocas, semilla 42.
3. No usar `any-in-window` como target multiclase. Clase de la última fila en todos
   los modelos supervisados; probabilidades en el orden del README.
4. Añadir adapter `LstmClassifier(Classifier)` con imports pesados lazy. El modo
   `lstm` del composition root debe seleccionar este adapter. Conservar
   `AnomalyClassifier` como auxiliar binario, sin presentarlo como modo multiclase.
5. Exportador: conservar `lstm_ae.pt` para el auxiliar y añadir `lstm_classifier.pt`
   para el supervisado. Conservar nombres existentes de XGBoost, scaler y encoder;
   versionar el contrato porque cambia su contenido. No escribir archivos exportados ahora.
6. Sustituir la exigencia binaria de `composition_root.py` por validación del contrato
   multiclase y del orden del encoder. `Agent` continúa consumiendo solo `Classifier`.
7. Alerts conservan el label exacto; `normal` no emite alerta. No inferir client ID/IP
   inexistentes en L2. No ampliar el formato de alertas salvo necesidad concreta.

## 4.2 Autoencoder auxiliar

- Encoder LSTM → latente repetido → decoder LSTM con hidden size 32 → proyección
  `Linear(32, num_tensor_features)`. Reconstruir exactamente el tensor documentado
  en fase 3, incluidas máscaras; MSE medio sobre tiempo y features de ese tensor.
- Entrenar solo ventanas completamente normales del train correspondiente.
- Referencia binaria: umbral percentil 95 del MSE de ventanas completamente normales
  de validation. El híbrido consume MSE continuo, no el label producido por el umbral.
- Si no hay ventanas normales de train/validation, registrar modelo/métrica no
  evaluable; no calibrar con ataques ni con test como sustitución.
- La regresión de 3.6 requiere comparación final controlada. No prometer que cambiar
  decoder o añadir máscaras recuperará un resultado concreto.

## 4.3 Tasa temporal por dirección

Reemplazar la fórmula instantánea de `fe_bytes_per_sec` por una definición única:
sumar `frame.len` de frames anteriores de la misma conexión/episodio y dirección
con tiempo en `[t-5,t]`, excluir el actual y dividir entre 5 segundos. Sin historial
→ 0. Publicar como `fe_bytes_per_sec = log1p(tasa)` y documentar unidades/transformación.

Mantener estado fuera del buffer de 11 frames: este no representa necesariamente
5 segundos. Reiniciar por conexión/episodio, captura o retroceso; calcular offline
dentro de partición. Para longitudes faltantes/inválidas, no sumar bytes inventados
y registrar el caso. No recalcular ni reemplazar `frame.time_delta` del wire.

Actualizar generador de features del notebook y builder online. No estimar la tasa
dividiendo por un delta diminuto ni introducir puertos como features.

## 4.4 Entropía y representación del payload

El diagnóstico histórico de fase 0 identifica `mqtt.msg` del CSV como texto, incluso
cuando contiene caracteres hexadecimales. No aplicar `bytes.fromhex` por apariencia.

Para este dataset conservar entropía sobre el texto original; el capturador convierte
los bytes de tshark a esa representación según su contrato vigente. Documentar la
limitación para bytes no UTF-8. Si se admite en el futuro otro formato, exigir un
modo explícito; no añadir autodetección heurística en esta fase. Escribir casos de
texto formado solo por dígitos hexadecimales para evitar una decodificación accidental.

## Evaluación que dejar preparada

- Métricas multiclase del LSTM supervisado separadas del AUC binario del autoencoder.
- Comparaciones de decoder/preprocesado auxiliar sobre la misma partición y tarea;
  no comparar macro-F1 binario histórico con macro-F1 de cuatro clases como mejora.
- Efecto de las features compartidas sobre XGBoost e híbrido, además de LSTM.
- No revertir automáticamente código ni publicar modelos basándose en test. Las
  configuraciones se seleccionan con validation; resultados y decisión final del usuario.

## Cierre de código

- [ ] Tres modos públicos con cuatro salidas y encoder común.
- [ ] Autoencoder auxiliar separado, decoder proyectado y MSE con contrato explícito.
- [ ] Tasa reproducible offline/online y representación de payload documentada.
- [ ] Exportación y carga programadas, sin generar ni reemplazar artefactos.
- [ ] Pendiente ejecutar y medir: no afirmar superioridad ni recuperación del LSTM.
