"""Features TCP del modelo B calculadas en línea, frame a frame.

Espejo incremental de ``ML_Model/data_preprocessing/tcp_features.build_tcp_features``:
mismas 12 columnas, mismo orden y mismas ventanas causales de 5 s (usan solo frames
anteriores; el frame actual no cuenta; sin historial el valor es 0). Solo usa la
biblioteca estándar para que el sidecar de captura no necesite numpy ni pandas.

Claves de agrupación, como en ``load_data.add_session_keys``:

- conexión = par de endpoints no dirigido + nº de CONNECT vistos en ese par (cada
  CONNECT abre una sesión nueva; los frames previos al primero son la sesión 0);
- dirección = conexión + ``(ip.src, tcp.srcport, ip.dst, tcp.dstport)``.

Piezas: ``frame`` valida el registro, ``windows`` implementa las ventanas y
``lru`` acota la memoria por flujo.
"""

from __future__ import annotations

import math

from capture.domain.frame import TcpFrame
from capture.domain.lru import LruDict
from capture.domain.windows import EventCounter, RollingStats
from wire.protocol import TCP_FEATURE_COLUMNS

DEFAULT_MAX_KEYS = 65536


class _Direction:
    """Estado de un sentido de una conexión: tamaños e inter-arrival times."""

    __slots__ = ('last_t', 'lengths', 'iats')

    def __init__(self):
        self.last_t = None
        self.lengths = RollingStats()
        self.iats = RollingStats()


class TcpWindowFeatures:
    """Calcula las 12 features TCP de cada frame a partir del registro de tshark."""

    def __init__(self, max_keys: int = DEFAULT_MAX_KEYS):
        # Par de endpoints -> nº de CONNECT vistos.
        self._sessions = LruDict(max_keys)

        # Dirección -> _Direction.
        self._directions = LruDict(max_keys)

        # Conexión -> RollingStats de flags "hacia el broker".
        self._connections = LruDict(max_keys)

        # Pares ya vistos hacia el broker y momento de su primera aparición.
        self._seen_pairs = LruDict(max_keys * 4)
        self._new_pairs = EventCounter()

    def update(self, record: dict) -> dict | None:
        """Features del frame (orden de ``TCP_FEATURE_COLUMNS``) o ``None`` si no aplica.

        Los registros deben llegar en orden de captura. Fuera de los puertos MQTT, o
        sin IP/puertos/tiempo válidos, devuelve ``None`` y no actualiza el estado.
        """
        frame = TcpFrame.from_record(record)
        if frame is None:
            return None

        endpoints = frame.endpoints
        session = self._session(frame, endpoints)
        connection_key = (endpoints, session)

        iat, iats, lengths = self._direction_windows(frame, connection_key)
        asymmetry = self._asymmetry(frame, connection_key)
        new_connections = self._new_connections(frame, endpoints)

        values = (
            frame.length,  # frame.len
            math.log1p(frame.length),  # fe_log_len
            frame.time_delta,  # frame.time_delta
            1.0,  # fe_is_standard_mqtt_port
            1.0 if frame.from_broker else 0.0,  # fe_is_broker_to_client
            iat,  # tcp_iat
            iats.std(),  # tcp_iat_std_5s
            float(lengths.count),  # tcp_frames_5s
            math.log1p(max(lengths.total, 0.0)),  # tcp_bytes_5s
            lengths.std(),  # tcp_len_std_5s
            asymmetry,  # tcp_asymmetry_5s
            float(new_connections),  # tcp_new_conns_5s
        )

        return {
            name: (value if math.isfinite(value) else 0.0)
            for name, value in zip(TCP_FEATURE_COLUMNS, values, strict=True)
        }

    def _session(self, frame: TcpFrame, endpoints) -> int:
        """Número de sesión del par; cada CONNECT abre una nueva."""
        session = self._sessions.get(endpoints, 0)

        if frame.is_connect:
            session += 1

        self._sessions.put(endpoints, session)

        return session

    def _direction_windows(self, frame: TcpFrame, connection_key):
        """IAT del frame y ventanas previas de IAT y tamaño en su dirección."""
        direction_key = (connection_key, *frame.direction)
        direction = self._directions.get_or_create(direction_key, _Direction)

        if direction.last_t is None:
            iat = 0.0
        else:
            iat = frame.time - direction.last_t

        # Primero se consulta la ventana (sin el frame actual) y luego se registra.
        lengths = direction.lengths.advance(frame.time)
        iats = direction.iats.advance(frame.time)

        direction.lengths.push(frame.time, frame.length)
        direction.iats.push(frame.time, iat)
        direction.last_t = frame.time

        return iat, iats, lengths

    def _asymmetry(self, frame: TcpFrame, connection_key) -> float:
        """Fracción de frames previos de la conexión que iban hacia el broker."""
        flags = self._connections.get_or_create(connection_key, RollingStats)

        ratio = flags.advance(frame.time).mean()

        flags.push(frame.time, 1.0 if frame.to_broker else 0.0)

        return ratio

    def _new_connections(self, frame: TcpFrame, endpoints) -> int:
        """Pares nuevos hacia el broker en los últimos 5 s (sin contar el actual)."""
        count = self._new_pairs.count(frame.time)

        is_new_pair = frame.to_broker and endpoints not in self._seen_pairs

        if is_new_pair:
            self._seen_pairs.put(endpoints, True)
            self._new_pairs.add(frame.time)

        return count
