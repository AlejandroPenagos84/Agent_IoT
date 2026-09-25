from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Iterator

from application.ports.ports_out import FeatureSource
from application.ports.types import Frame

DEFAULT_WINDOW_SECONDS = 5.0
DEFAULT_L2_EPISODE_GAP_SECONDS = 1.0

# Limite de claves activas (ip / eth.src / direccion) retenidas por el estado causal.
MAX_TRACKED_KEYS = 4096

ORIGIN_TRANSPORTS = (
    '_ctx_origen_frames_s',
    '_ctx_origen_bytes_s',
    '_ctx_origen_conexiones',
    '_ctx_origen_connects',
)

L2_RATE_TRANSPORTS = (
    '_ctx_l2_frames_s',
    '_ctx_l2_broadcasts',
    '_ctx_l2_burst_ratio',
)
BROADCAST_MAC = 'ff:ff:ff:ff:ff:ff'
BURST_DELTA_SECONDS = 100e-6

# Fase 4.3: tasa causal de bytes por conexion/episodio y direccion.
DIRECTION_RATE_TRANSPORT = '_ctx_bytes_per_s'


def _multicast_flag(value):
    """Return the multicast bit of the first octet, NaN when absent/invalid."""
    if value is None:
        return float('nan')
    text = str(value).strip().lower()
    if not text:
        return float('nan')
    try:
        return int(text.split(':')[0], 16) & 1
    except (ValueError, IndexError):
        return float('nan')


def _normalized(value):
    """Normalize a MAC/IP the way the offline path does."""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _port_in_range(value) -> bool:
    """True when a port is an integer between 1 and 65535."""
    try:
        port = int(value)
    except (TypeError, ValueError):
        return False
    return 1 <= port <= 65535


def _observable_tcp(context) -> bool:
    """Mirror the offline TCP admission: finite clock, endpoints and ports."""
    ts = context.ts
    return (ts is not None and ts == ts
            and bool(context.ip) and bool(context.dst_ip)
            and _port_in_range(context.srcport)
            and _port_in_range(context.dstport))


class ContextFeatureSource(FeatureSource):
    """Decorate a FeatureSource with causal per-origin context windows.

    Frames arrive in temporal order. The statistics for a frame only use earlier
    frames in stream order whose ``frame.time_epoch`` falls inside the last
    ``window_seconds``. The current frame never contributes to its own features.
    Frames without ``ip.src`` get NaN for the origin features.
    """

    def __init__(self, source: FeatureSource,
                 window_seconds: float = DEFAULT_WINDOW_SECONDS,
                 l2_episode_gap_seconds: float = DEFAULT_L2_EPISODE_GAP_SECONDS):
        self.source = source
        self.window_seconds = float(window_seconds)
        self.l2_episode_gap_seconds = float(l2_episode_gap_seconds)
        self._origin: dict = {}
        self._l2: dict = {}
        self._direction: dict = {}
        self._l2_last_seen: dict = {}
        self._l2_episode: dict = {}
        self._tcp_sessions: dict = {}

    def start(self) -> None:
        self.source.start()
        self._origin.clear()
        self._l2.clear()
        self._direction.clear()
        self._l2_last_seen.clear()
        self._l2_episode.clear()
        self._tcp_sessions.clear()

    def stop(self) -> None:
        self.source.stop()

    @staticmethod
    def _epoch(features) -> float | None:
        try:
            epoch = float(features.get('frame.time_epoch'))
        except (TypeError, ValueError):
            return None
        return epoch if epoch == epoch else None

    @staticmethod
    def _length(features) -> float:
        try:
            length = float(features.get('frame.len'))
        except (TypeError, ValueError):
            return 0.0
        return length if length == length else 0.0

    @staticmethod
    def _is_connect(features) -> int:
        try:
            return 1 if int(float(features.get('mqtt.msgtype'))) == 1 else 0
        except (TypeError, ValueError):
            return 0

    def _origin_features(self, context, epoch: float | None, features) -> dict:
        ip = context.ip
        if not ip or epoch is None:
            return {name: float('nan') for name in ORIGIN_TRANSPORTS}
        if ip not in self._origin:
            self._origin[ip] = deque()
            while len(self._origin) > MAX_TRACKED_KEYS:
                self._origin.pop(next(iter(self._origin)))
        events = self._origin[ip]
        if events and epoch < events[-1]['epoch']:
            events.clear()
        while events and epoch - events[0]['epoch'] > self.window_seconds:
            events.popleft()
        if events:
            result = {
                '_ctx_origen_frames_s': len(events) / self.window_seconds,
                '_ctx_origen_bytes_s': sum(e['len'] for e in events) / self.window_seconds,
                '_ctx_origen_conexiones': len({e['conn'] for e in events}),
                '_ctx_origen_connects': sum(e['connect'] for e in events),
            }
        else:
            result = {name: 0.0 for name in ORIGIN_TRANSPORTS}
        connection = context.stream_id
        if connection is None:
            connection = (context.ip, context.srcport, context.dst_ip, context.dstport)
        events.append({'epoch': epoch, 'len': self._length(features),
                       'conn': connection, 'connect': self._is_connect(features)})
        return result

    def _l2_features(self, context, epoch: float | None, features) -> dict:
        dest = (str(context.eth_dst).strip().lower()
                if context.eth_dst is not None else None)
        if dest:
            is_multicast = _multicast_flag(dest)
            # Destino invalido (primer octeto no hexadecimal) no es unicast valido.
            is_broadcast = (1.0 if dest == BROADCAST_MAC else 0.0
                            if is_multicast == is_multicast else float('nan'))
        else:
            is_broadcast = float('nan')
            is_multicast = float('nan')
        result = {'_ctx_is_broadcast': float(is_broadcast),
                  '_ctx_is_multicast': float(is_multicast)}
        source = (str(context.eth_src).strip().lower()
                  if context.eth_src is not None else None)
        if not source or epoch is None:
            result.update({name: float('nan') for name in L2_RATE_TRANSPORTS})
            return result
        if source not in self._l2:
            self._l2[source] = deque()
            while len(self._l2) > MAX_TRACKED_KEYS:
                self._l2.pop(next(iter(self._l2)))
        events = self._l2[source]
        if events and epoch < events[-1]['epoch']:
            events.clear()
        while events and epoch - events[0]['epoch'] > self.window_seconds:
            events.popleft()
        if events:
            deltas = [events[index]['epoch'] - events[index - 1]['epoch']
                      for index in range(1, len(events))]
            result['_ctx_l2_frames_s'] = len(events) / self.window_seconds
            result['_ctx_l2_broadcasts'] = sum(e['broadcast'] for e in events)
            result['_ctx_l2_burst_ratio'] = (
                sum(delta < BURST_DELTA_SECONDS for delta in deltas) / len(deltas)
                if deltas else 0.0)
        else:
            result.update({name: 0.0 for name in L2_RATE_TRANSPORTS})
        events.append({'epoch': epoch,
                       'broadcast': 0.0 if is_broadcast != is_broadcast
                       else float(is_broadcast)})
        return result

    def _episode(self, pair, epoch) -> int:
        """Track causal L2 episodes per unordered MAC pair (gap > 1 s or rollback)."""
        previous = self._l2_last_seen.get(pair)
        if (previous is None or epoch is None or epoch < previous
                or epoch - previous > self.l2_episode_gap_seconds):
            self._l2_episode[pair] = self._l2_episode.get(pair, 0) + 1
        if epoch is not None:
            self._l2_last_seen[pair] = epoch
        while len(self._l2_last_seen) > MAX_TRACKED_KEYS:
            old_pair = next(iter(self._l2_last_seen))
            self._l2_last_seen.pop(old_pair, None)
            self._l2_episode.pop(old_pair, None)
        return self._l2_episode.get(pair, 1)

    def _direction_key(self, context, features):
        """Identify connection/episode plus direction, offline ``_direction`` style.

        Online uses ``tcp.stream``. When the capture has no ``tcp.stream`` (as in
        the offline CSV replay) the TCP session is approximated with the same
        cumulative CONNECT counter as the notebook's ``_connection``.
        """
        if _observable_tcp(context):
            if context.stream_id is not None:
                return ('tcp', context.stream_id, context.ip, context.srcport,
                        context.dst_ip, context.dstport)
            endpoint = tuple(sorted(((str(context.ip), int(context.srcport)),
                                     (str(context.dst_ip), int(context.dstport)))))
            if self._is_connect(features):
                self._tcp_sessions[endpoint] = self._tcp_sessions.get(endpoint, 0) + 1
                while len(self._tcp_sessions) > MAX_TRACKED_KEYS:
                    self._tcp_sessions.pop(next(iter(self._tcp_sessions)))
            session = self._tcp_sessions.get(endpoint, 0)
            return ('tcp', endpoint, session, context.ip, context.srcport,
                    context.dst_ip, context.dstport)
        source = _normalized(context.eth_src)
        destination = _normalized(context.eth_dst)
        if source is None or destination is None:
            return None
        pair = tuple(sorted((source, destination)))
        return ('l2', self._episode(pair, context.ts), source, destination)

    def _direction_rate(self, context, epoch, features) -> dict:
        """Causal bytes/s over the last 5 s of the same connection and direction.

        The current frame is excluded; its missing length is never replaced by
        invented bytes. Without history the rate is 0 (``log1p(0) == 0``).
        """
        key = self._direction_key(context, features)
        raw_length = features.get('frame.len')
        try:
            length = float(raw_length)
        except (TypeError, ValueError):
            length = None
        if length is not None and length != length:
            length = None
        if key is None or epoch is None:
            return {DIRECTION_RATE_TRANSPORT: 0.0}
        if key not in self._direction:
            self._direction[key] = deque()
            while len(self._direction) > MAX_TRACKED_KEYS:
                self._direction.pop(next(iter(self._direction)))
        events = self._direction[key]
        if events and epoch < events[-1]['epoch']:
            events.clear()
        while events and epoch - events[0]['epoch'] > self.window_seconds:
            events.popleft()
        rate = sum(event['len'] for event in events) / self.window_seconds
        if length is not None:
            events.append({'epoch': epoch, 'len': length})
        return {DIRECTION_RATE_TRANSPORT: rate}

    def rows(self) -> Iterator[Frame]:
        for frame in self.source.rows():
            features = dict(frame.features)
            epoch = self._epoch(features)
            features.update(self._origin_features(frame.context, epoch, features))
            features.update(self._l2_features(frame.context, epoch, features))
            features.update(self._direction_rate(frame.context, epoch, features))
            yield replace(frame, features=features)
