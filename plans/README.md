# Plan de implementación — MQTT_UAD, L2 y cuatro clases

## Instrucción del usuario y límites

Este directorio contiene instrucciones para una implementación futura. Crear estos
documentos no autoriza a implementar el proyecto en la sesión que los redacta.

Cuando el usuario encargue implementar el plan, el agente debe leer este archivo y
las seis fases y la fase editorial del notebook. Su trabajo será **escribir código, pruebas y documentación, sin
ejecutar el proyecto**. El usuario ejecutará todo al terminar la implementación.

- Permitido: leer y buscar archivos; editar código, celdas y documentación; escribir
  pruebas y el procedimiento de validación; inspeccionar estáticamente los cambios.
- Prohibido al agente: ejecutar celdas, entrenamientos, inferencia, tests,
  `py_compile`, validadores, smoke tests, dry-runs, capturas, broker o contenedores;
  instalar dependencias; generar resultados o artefactos ML.
- Se permiten herramientas de edición del notebook que únicamente lean/escriban
  su estructura, sin ejecutar sus celdas ni importar módulos del proyecto.
- No ejecutar por fase. No exigir métricas, tests aprobados ni confirmación entre
  fases para continuar escribiendo el código autorizado.
- No crear commits ni modificar resultados históricos como parte de este plan.
- No editar, eliminar ni reemplazar `modelos_agente/`. El usuario actualizará el
  conjunto completo al final, después de ejecutar y revisar la validación.
- Los artefactos antiguos son esperables durante el desarrollo. No desactivar las
  validaciones de compatibilidad para conseguir que carguen con código nuevo.

Estas reglas expresan la instrucción actual del usuario y sustituyen, para este
trabajo, las instrucciones anteriores de ejecutar por fase, detenerse por métricas,
pedir nuevamente A/B, hacer commits o actualizar artefactos junto a cada cambio.
`infrastructure/CLAUDE.md` es contexto histórico, no una segunda secuencia de trabajo.
Se mantienen la arquitectura hexagonal y los imports pesados lazy de `AGENTS.md`.

## Referencia y alcance

Fecha de inspección estática: 2026-09-21. El código vigente es la referencia de lo
implementado. Los reportes son evidencia histórica, no verificaciones de esta sesión.
No copiar implementaciones desde `tmp/` sin contrastarlas con el código principal.

El notebook actual trabaja con MQTT visible y contexto Ethernet TCP/L2. Este plan
conserva ese alcance y no afirma soporte validado de MQTTS. No eliminar features MQTT
para cumplir una descripción antigua de cifrado, ni presentar campos MQTT como
observables dentro de TLS. No ampliar `TlsClassifier` ni el simulador en este trabajo.

Objetivo final: notebook e infraestructura coherentes para clasificar como
`normal`, `DoS`, `mitm` o `intrusion`, conservando frames L2 observables y sin usar
identidades crudas como features. L2 es una categoría de observación, no una etiqueta
de ataque. No asignar `mitm` por carecer de IP, ser broadcast o pertenecer a un CSV.

## Orden y estado de partida

| Fase | Estado observado | Trabajo encargado |
| --- | --- | --- |
| [0 — Base y L2](fase-0.md) | Implementada y con reportes históricos | Conservar contratos; completar diagnósticos finales faltantes |
| [1 — Pesos](fase-1.md) | Implementada; modelos todavía binarios | Preservar balanceo; no confundirlo con clasificación multiclase |
| [2 — Orígenes](fase-2.md) | Implementada parcialmente respecto al contrato final | Refinar ausencia de identidad y paridad offline/online |
| [3 — Contexto y faltantes](fase-3.md) | 3.1–3.6 presentes; problemas de paridad y regresión documentados | Refinar y escribir comprobaciones completas |
| [4 — Modelos](fase-4.md) | Pendiente del objetivo nuevo | Cuatro clases, LSTM supervisado, autoencoder auxiliar y features temporales |
| [5 — Evaluación y entrega](fase-5.md) | Pendiente | Escribir evaluación, validación y exportación final para el usuario |
| [Notebook — Legibilidad](fase-notebook.md) | Plan editorial sobre la versión vigente | Dividir celdas y mejorar explicaciones sin eliminar ni cambiar código |

Leer 4 y 5 antes de editar 2 y 3: definen consumidores, preprocesado y particiones.
Implementar en orden 0 → 1 → 2 → 3 → 4 → 5, sin ejecuciones intermedias.
Después aplicar la fase notebook y entregar al usuario para su ejecución final.
Si se encarga solo la fase notebook, no implementar ni reabrir las fases funcionales.
Una tarea ya satisfecha por el código se conserva; no se reescribe por cumplir una lista.

## Decisiones comunes obligatorias

1. Clases canónicas y orden de probabilidades: `['normal', 'DoS', 'mitm', 'intrusion']`.
   Normalizar mayúsculas/espacios de entrada mediante un mapa explícito. Rechazar
   etiquetas desconocidas. Guardar el mismo mapa en encoder y config exportados.
2. Los tres modos públicos (`xgboost`, `lstm`, `hybrid`) producirán cuatro clases.
   Para cumplirlo, el modo `lstm` será supervisado. El autoencoder actual se conserva
   como auxiliar del híbrido y referencia binaria, no se lo renombra como multiclase.
   Esta es una decisión de diseño del plan; no describe el código actual.
3. La etiqueta supervisada de una ventana corresponde a su última fila. La condición
   «toda la ventana normal» se conserva solo para entrenar/calibrar el autoencoder.
4. Conservar `SEED=42`, agrupación por conexión/episodio, secuencias de 10 y primera
   predicción tras 11 frames por dirección. Mantener ese comportamiento del agente
   también para XGBoost; reportar por separado su evaluación offline por frame.
5. Ninguna ventana cruza captura, conexión/episodio, dirección o partición. Estado
   por origen/MAC sí cruza conexiones, pero nunca capturas independientes o particiones.
6. Features aprendidas, vocabularios, medias y scalers usan solo el train correspondiente.
   Validation sirve para calibración/selección; test no decide cambios ni exportación.
7. Conservar `FILES`, rutas Kaggle, `OUT_DIR` y ruta ZIP originales del notebook.
   La ejecución local futura usará una copia y rutas explícitas elegidas por el usuario.
8. IP, MAC, client ID, reloj absoluto y puertos crudos pueden ser contexto interno,
   nunca entradas crudas del modelo. No inventar campos ARP ausentes del dataset.
9. El notebook debe seguir siendo ejecutable en Kaggle sin depender del checkout de
   `infrastructure/`. Si se mantienen funciones espejo, escribir pruebas de paridad.
10. Toda modificación de features debe actualizar el **código que genera** el config,
    listas y tablas del notebook, y los adapters. No editar el config ya exportado.

## Significado de terminado

- **Código preparado:** cambios y pruebas escritos, revisión estática realizada,
  ejecución pendiente del usuario. Es el máximo estado que puede declarar el agente.
- **Validado:** solo después de una ejecución del usuario con evidencia identificable.
- **Aceptado para despliegue:** decisión del usuario sobre un paquete final coherente.

El informe de entrega enumerará archivos cambiados, comandos que ejecutará el usuario
y limitaciones pendientes. Debe decir «No se ejecutaron pruebas ni entrenamientos».
Nunca inventar métricas ni copiar resultados históricos como si fueran del código nuevo.
