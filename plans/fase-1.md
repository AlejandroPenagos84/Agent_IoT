# Fase 1 — Preservar pesos por clase

Leer primero [README.md](README.md). Fase existente; no repetir entrenamientos.

## Evidencia y alcance

El notebook ya implementa `fit_classifier(features, labels, labels_4clases)` con
`compute_sample_weight('balanced', labels_4clases)`. Se usa para XGBoost de frames
y el híbrido. `reports/fase1.md` documenta ese cambio sobre targets binarios.

**Esta fase está implementada en su alcance original. No significa que los modelos
actuales distingan cuatro clases.** La migración de targets y salidas es fase 4.
El reporte histórico también registra aumento de falsos positivos superior al límite
anterior: no declarar cumplida la aceptación de rendimiento de aquel plan.

## Qué hacer

1. Conservar pesos por las clases originales, nunca por una etiqueta binaria agregada.
2. Comprobar estáticamente correspondencia entre filas, targets y pesos:
   frames de train para XGBoost; última fila de ventana para el híbrido.
3. Al implementar fase 4, simplificar la firma si target y clase de ponderación ya
   coinciden. Mantener la semántica; no duplicar ponderación ni balancear con test.
4. En fase 5, calcular pesos sobre las muestras que efectivamente ajustan cada modelo
   o fold interno. No reutilizar pesos calculados sobre el dataset completo.
5. Para el LSTM supervisado de fase 4, usar pesos de clase derivados exclusivamente
   de los targets finales de sus ventanas de train. No aplicarlos al autoencoder.

## Pruebas que escribir o conservar, sin ejecutar

- Correspondencia exacta entre target, fila final y peso.
- Cambiar etiquetas de validation/test no cambia los pesos de train.
- Una clase ausente se registra explícitamente; no generar pesos infinitos ni
  inventar muestras para completar cuatro clases.

## Cierre de código

- [ ] Se conserva el balanceo ya implementado.
- [ ] Ningún reporte binario se presenta como resultado multiclase.
- [ ] No se ajustan pesos buscando compensar métricas históricas de test.
- [ ] La implementación puede continuar a fase 2 sin ejecutar esta fase.
