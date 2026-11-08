"""Campos del wire compartidos por captura, fuentes y clasificadores."""

# Campos que se le piden a tshark con `-e`. Solo los mínimos para calcular las
# features TCP y el contexto de la alerta.
CAPTURE_FIELDS = (
    'frame.time_epoch',
    'frame.time_delta',
    'frame.len',
    'ip.src',
    'ip.dst',
    'tcp.srcport',
    'tcp.dstport',
    'tcp.stream',
    'mqtt.msgtype',
    'mqtt.clientid',
    'mqtt.topic',
)

# Campos del registro que se envía al agente. `mqtt.msgtype` solo lo necesita
# TcpWindowFeatures en la captura; el agente recibe las features ya calculadas.
RECORD_FIELDS = tuple(f for f in CAPTURE_FIELDS if f != 'mqtt.msgtype') + (
    'tcp_features',
)
