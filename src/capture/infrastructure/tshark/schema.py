"""Campos que la captura le pide a tshark y su tipo."""

from wire.protocol import RECORD_FIELDS

# Campos que se le piden a tshark con `-e`: los del registro del contrato más
# `mqtt.msgtype`, que solo usa TcpWindowFeatures en la captura (el agente recibe
# las features ya calculadas).
CAPTURE_FIELDS = tuple(f for f in RECORD_FIELDS if f != 'tcp_features') + ('mqtt.msgtype',)

FLOAT_FIELDS = frozenset({'frame.time_epoch', 'frame.time_delta', 'frame.len'})
INT_FIELDS = frozenset({'tcp.srcport', 'tcp.dstport', 'tcp.stream'})

__all__ = ['CAPTURE_FIELDS', 'FLOAT_FIELDS', 'INT_FIELDS', 'RECORD_FIELDS']
