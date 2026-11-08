"""Features TCP del modelo B calculadas en línea, frame a frame.

Espejo incremental de ``ML_Model/data_preprocessing/tcp_features.build_tcp_features``:
mismas 12 columnas, mismo orden y mismas ventanas causales de 5 s (usan solo frames
anteriores; el frame actual no cuenta; sin historial el valor es 0). Solo usa la
biblioteca estándar para que el sidecar de captura no necesite numpy ni pandas.

El modelo se entrenó solo con frames que tienen puerto 1883/8883 en origen o destino
(``training_scope = mqtt_ports``) y sus ventanas se calcularon solo con esos frames.
Por eso ``update`` devuelve ``None`` para cualquier otro frame y no lo usa como
historial.

Claves de agrupación, como en ``load_data.add_session_keys``:

- conexión = par de endpoints no dirigido + nº de CONNECT vistos en ese par (cada
  CONNECT abre una sesión nueva; los frames previos al primero son la sesión 0);
- dirección = conexión + ``(ip.src, tcp.srcport, ip.dst, tcp.dstport)``.

IP, puertos y ``frame.time_epoch`` solo son claves y reloj, nunca features.
"""

from __future__ import annotations

import math
from collections import OrderedDict, deque

MQTT_PORTS = (1883, 8883)
WINDOW_SECONDS = 5.0
CONNECT_TYPE = 1

# Mismo orden que TCP_FEATURE_COLUMNS del notebook; cambiarlo obliga a reentrenar.
TCP_FEATURE_COLUMNS = (
    'frame.len', 'fe_log_len', 'frame.time_delta',
    'fe_is_standard_mqtt_port', 'fe_is_broker_to_client',
    'tcp_iat', 'tcp_iat_std_5s',
    'tcp_frames_5s', 'tcp_bytes_5s', 'tcp_len_std_5s',
    'tcp_asymmetry_5s', 'tcp_new_conns_5s',
)

DEFAULT_MAX_KEYS = 65536


def _number(value, default=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _port(value):
    result = _number(value)
    return int(result) if result is not None and result.is_integer() else None


def _std(count, total, squares):
    if count <= 0:
        return 0.0
    mean = total / count
    return math.sqrt(max(squares / count - mean * mean, 0.0))


class _Rolling:
    """Conteo, suma y suma de cuadrados de los valores anteriores en la ventana.

    Replica ``_rolling_previous``: primero entra el valor del frame anterior y
    luego salen los que tienen ``t <= ahora - ventana``.
    """

    __slots__ = ('items', 'pending', 'count', 'total', 'squares')

    def __init__(self):
        self.items = deque()      # (t, valor) ya incluidos en la ventana
        self.pending = None       # (t, valor) del frame anterior, aún no incluido
        self.count = 0
        self.total = 0.0
        self.squares = 0.0

    def query(self, now, window=WINDOW_SECONDS):
        if self.pending is not None:
            t, value = self.pending
            self.items.append((t, value))
            self.count += 1
            self.total += value
            self.squares += value * value
            self.pending = None
        limit = now - window
        while self.items and self.items[0][0] <= limit:
            _, value = self.items.popleft()
            self.count -= 1
            self.total -= value
            self.squares -= value * value
        return self.count, self.total, self.squares

    def push(self, t, value):
        self.pending = (t, value)


class _Direction:
    __slots__ = ('last_t', 'lengths', 'iats')

    def __init__(self):
        self.last_t = None
        self.lengths = _Rolling()
        self.iats = _Rolling()


class _Connection:
    """Ventana de flags cliente->broker de los frames anteriores de la conexión."""

    __slots__ = ('items', 'pending', 'total', 'to_broker')

    def __init__(self):
        self.items = deque()
        self.pending = None
        self.total = 0
        self.to_broker = 0.0

    def ratio(self, now):
        if self.pending is not None:
            self.items.append(self.pending)
            self.total += 1
            self.to_broker += self.pending[1]
            self.pending = None
        limit = now - WINDOW_SECONDS
        while self.items and self.items[0][0] <= limit:
            _, flag = self.items.popleft()
            self.total -= 1
            self.to_broker -= flag
        return self.to_broker / self.total if self.total > 0 else 0.0

    def push(self, t, flag):
        self.pending = (t, flag)


class _BoundedDict(OrderedDict):
    """Dict con expulsión del elemento usado hace más tiempo."""

    def __init__(self, max_size):
        super().__init__()
        self.max_size = max_size

    def get_or_create(self, key, factory):
        value = self.get(key)
        if value is None:
            value = factory()
            self[key] = value
            if len(self) > self.max_size:
                self.popitem(last=False)
        else:
            self.move_to_end(key)
        return value


class TcpWindowFeatures:
    """Calcula las 12 features TCP de cada frame a partir del registro de tshark."""

    def __init__(self, max_keys: int = DEFAULT_MAX_KEYS):
        self._sessions = _BoundedDict(max_keys)      # par de endpoints -> nº de CONNECT
        self._directions = _BoundedDict(max_keys)
        self._connections = _BoundedDict(max_keys)
        self._seen_pairs = _BoundedDict(max_keys * 4)  # pares ya vistos hacia el broker
        self._new_pairs = deque()                      # t de primera aparición

    @staticmethod
    def in_scope(record: dict) -> bool:
        """True si el frame tiene puerto 1883/8883 en origen o destino."""
        return (_port(record.get('tcp.srcport')) in MQTT_PORTS
                or _port(record.get('tcp.dstport')) in MQTT_PORTS)

    def update(self, record: dict) -> dict | None:
        """Features del frame (orden de ``TCP_FEATURE_COLUMNS``) o ``None`` si no aplica.

        Los registros deben llegar en orden de captura. Fuera de la vista `mqtt`, o
        sin IP/puertos/tiempo válidos, devuelve ``None`` y no actualiza el estado.
        """
        now = _number(record.get('frame.time_epoch'))
        src_ip, dst_ip = record.get('ip.src'), record.get('ip.dst')
        src_port, dst_port = _port(record.get('tcp.srcport')), _port(record.get('tcp.dstport'))
        if now is None or not src_ip or not dst_ip or src_port is None or dst_port is None:
            return None
        to_broker = dst_port in MQTT_PORTS
        from_broker = src_port in MQTT_PORTS
        if not (to_broker or from_broker):
            return None

        frame_len = _number(record.get('frame.len'), 0.0)
        time_delta = max(_number(record.get('frame.time_delta'), 0.0), 0.0)

        endpoints = tuple(sorted(((str(src_ip), src_port), (str(dst_ip), dst_port))))
        session = self._sessions.get(endpoints, 0)
        if _number(record.get('mqtt.msgtype')) == CONNECT_TYPE:
            session += 1
        self._sessions[endpoints] = session
        self._sessions.move_to_end(endpoints)
        if len(self._sessions) > self._sessions.max_size:
            self._sessions.popitem(last=False)
        connection_key = (endpoints, session)
        direction_key = (connection_key, str(src_ip), src_port, str(dst_ip), dst_port)

        # Ventanas por dirección.
        direction = self._directions.get_or_create(direction_key, _Direction)
        iat = 0.0 if direction.last_t is None else now - direction.last_t
        count, total, squares = direction.lengths.query(now)
        iat_count, iat_total, iat_squares = direction.iats.query(now)
        direction.lengths.push(now, frame_len)
        direction.iats.push(now, iat)
        direction.last_t = now

        # Asimetría por conexión.
        connection = self._connections.get_or_create(connection_key, _Connection)
        asymmetry = connection.ratio(now)
        connection.push(now, 1.0 if to_broker else 0.0)

        # Pares nuevos hacia el broker en los últimos 5 s (sin contar el actual).
        limit = now - WINDOW_SECONDS
        while self._new_pairs and self._new_pairs[0] <= limit:
            self._new_pairs.popleft()
        new_connections = float(len(self._new_pairs))
        if to_broker and endpoints not in self._seen_pairs:
            self._seen_pairs.get_or_create(endpoints, lambda: True)
            self._new_pairs.append(now)

        values = (
            frame_len, math.log1p(frame_len), time_delta,
            1.0, 1.0 if from_broker else 0.0,
            iat, _std(iat_count, iat_total, iat_squares),
            float(count), math.log1p(max(total, 0.0)), _std(count, total, squares),
            asymmetry, new_connections,
        )
        return {name: (value if math.isfinite(value) else 0.0)
                for name, value in zip(TCP_FEATURE_COLUMNS, values)}
