# Agente

`Agent` consume `Frame` por el port `FeatureSource`, mantiene ventanas de 11
filas y publica la última clasificación distinta de `normal` por `AlertSink`.
Depende solo de los ports y tipos compartidos.

Por defecto, los buffers se separan por conexión y dirección:
`(stream_id, ip, srcport, dst_ip, dstport)`. `stream_id` corresponde a
`tcp.stream`; evita mezclar conexiones que reutilizan endpoints en una captura.
No se mezclan respuestas del broker a distintos clientes.

Si un frame no tiene endpoints TCP completos, el agente usa el contexto L2:
mantiene episodios por par MAC no dirigido y ventanas separadas por dirección
`eth_src → eth_dst`. Un gap estrictamente mayor que
`l2_episode_gap_seconds` (1 segundo en los artefactos actuales), o un retroceso
del reloj, reinicia los buffers de ambas direcciones. Se omiten únicamente los
frames que no tienen contexto TCP completo ni MAC/reloj completos.
`per_flow=False` permite una ventana global.

Los adaptadores deben devolver su última etiqueta para el último frame de la
ventana, cuyo contexto se conserva para la alerta. Los LSTM evalúan también la
última secuencia completa. Una alerta sobre tráfico broker → cliente conserva
la IP del broker: `ip` identifica el origen del frame, no al atacante.

Verificación de regresiones: `python -m unittest discover -s tests -v`.
