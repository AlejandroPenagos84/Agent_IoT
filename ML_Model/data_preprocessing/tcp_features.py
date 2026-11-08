"""Features TCP/IP-only (opción B) para el experimento A/B del notebook.

Todas las features se calculan de forma causal: usan el frame actual y frames
anteriores, nunca posteriores. Las ventanas de 5 s excluyen el frame actual; sin
historial el valor es 0. IP, puertos y `frame.time_epoch` solo se usan como
claves de agrupación/orden, nunca como features del modelo.

El módulo asume el contrato de `load_data.add_session_keys`:
`_connection`, `_direction` y `_capture` ya construidos. `_direction` contiene
`(connection, ip_origen, puerto_origen, ip_destino, puerto_destino)`; de ahí se
extraen los pares de endpoints para `tcp_new_conns_5s`. Si el DataFrame trae
`ip.src`/`ip.dst`, también se pueden construir las claves a partir de ellos.
"""

from collections import deque

import numpy as np
import pandas as pd

MQTT_PORTS = (1883, 8883)
WINDOW_SECONDS = 5.0

# Orden fijo de la opción B. Cambiarlo obliga a reentrenar y reexportar.
TCP_FEATURE_COLUMNS = [
    'frame.len', 'fe_log_len', 'frame.time_delta',
    'fe_is_standard_mqtt_port', 'fe_is_broker_to_client',
    'tcp_iat', 'tcp_iat_std_5s',
    'tcp_frames_5s', 'tcp_bytes_5s', 'tcp_len_std_5s',
    'tcp_asymmetry_5s', 'tcp_new_conns_5s',
]


def _numeric(df, column):
    """Columna numérica o una serie de NaN si no existe."""
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors='coerce')


def _factorize(values):
    """Códigos enteros estables para claves (tuples, strings, etc.)."""
    mapping = {}
    codes = np.empty(len(values), dtype=np.int64)
    for position, value in enumerate(values):
        code = mapping.get(value)
        if code is None:
            code = len(mapping)
            mapping[value] = code
        codes[position] = code
    return codes


def _endpoint_pair(direction):
    """Par de endpoints no dirigido a partir de `_direction` o de un 4-tuple."""
    if isinstance(direction, (tuple, list)):
        if len(direction) == 5:
            _, source_ip, source_port, dest_ip, dest_port = direction
            return tuple(sorted((
                (str(source_ip), int(source_port)),
                (str(dest_ip), int(dest_port)),
            )))
        if len(direction) == 4:
            source_ip, source_port, dest_ip, dest_port = direction
            return tuple(sorted((
                (str(source_ip), int(source_port)),
                (str(dest_ip), int(dest_port)),
            )))
    return direction


def _previous_delta(times, groups):
    """Diferencia con el frame anterior dentro de cada captura."""
    result = np.zeros(len(times), dtype=float)
    for code in np.unique(groups):
        positions = np.where(groups == code)[0]
        positions = positions[np.argsort(times[positions], kind='stable')]
        if len(positions) > 1:
            result[positions[1:]] = np.diff(times[positions])
    return result


def _rolling_previous(times, values, window=WINDOW_SECONDS):
    """Conteo, suma y suma de cuadrados de frames anteriores en la ventana."""
    size = len(times)
    counts = np.zeros(size, dtype=float)
    totals = np.zeros(size, dtype=float)
    total_squares = np.zeros(size, dtype=float)

    left = 0
    count = 0
    total = 0.0
    squares = 0.0
    for position in range(size):
        if position > 0:
            value = values[position - 1]
            count += 1
            total += value
            squares += value * value

        limit = times[position] - window
        while left < position and times[left] <= limit:
            value = values[left]
            count -= 1
            total -= value
            squares -= value * value
            left += 1

        counts[position] = count
        totals[position] = total
        total_squares[position] = squares

    return counts, totals, total_squares


def _std(counts, totals, total_squares):
    """Desviación estándar a partir de conteo/suma/suma de cuadrados."""
    mean = np.divide(totals, counts, out=np.zeros_like(totals), where=counts > 0)
    variance = np.divide(
        total_squares, counts, out=np.zeros_like(total_squares), where=counts > 0
    ) - mean * mean
    return np.sqrt(np.clip(variance, 0.0, None))


def _direction_features(work):
    """Features de ventana por `_direction` (misma conexión y sentido)."""
    size = len(work)
    iat = np.zeros(size, dtype=float)
    frames_5s = np.zeros(size, dtype=float)
    bytes_5s = np.zeros(size, dtype=float)
    len_std = np.zeros(size, dtype=float)
    iat_std = np.zeros(size, dtype=float)

    positions = work['pos'].to_numpy()
    codes = work['direction_code'].to_numpy()
    times = work['t'].to_numpy(dtype=float)
    lengths = work['frame_len'].to_numpy(dtype=float)

    start = 0
    while start < size:
        end = start + 1
        code = codes[start]
        while end < size and codes[end] == code:
            end += 1

        original = positions[start:end]
        group_times = times[start:end]
        group_lengths = lengths[start:end]

        inter_arrival = np.zeros(end - start, dtype=float)
        if len(inter_arrival) > 1:
            inter_arrival[1:] = np.diff(group_times)
        iat[original] = inter_arrival

        counts, sums, squares = _rolling_previous(group_times, group_lengths)
        frames_5s[original] = counts
        bytes_5s[original] = np.log1p(np.maximum(sums, 0.0))
        len_std[original] = _std(counts, sums, squares)

        iat_counts, iat_sums, iat_squares = _rolling_previous(
            group_times, inter_arrival)
        iat_std[original] = _std(iat_counts, iat_sums, iat_squares)

        start = end

    return iat, frames_5s, bytes_5s, len_std, iat_std


def _connection_features(work):
    """Asimetría cliente->broker / total de la conexión en la ventana."""
    size = len(work)
    asymmetry = np.zeros(size, dtype=float)

    order = work.sort_values(
        ['capture_code', 'connection_code', 't', 'pos'], kind='stable')
    positions = order['pos'].to_numpy()
    codes = order['connection_code'].to_numpy()
    times = order['t'].to_numpy(dtype=float)
    client_to_broker = order['is_client_to_broker'].to_numpy(dtype=float)

    start = 0
    while start < size:
        end = start + 1
        code = codes[start]
        while end < size and codes[end] == code:
            end += 1

        group_times = times[start:end]
        group_flags = client_to_broker[start:end]
        group_size = end - start
        ratio = np.zeros(group_size, dtype=float)

        left = 0
        total = 0
        broker_bound = 0.0
        for position in range(group_size):
            if position > 0:
                total += 1
                broker_bound += group_flags[position - 1]

            limit = group_times[position] - WINDOW_SECONDS
            while left < position and group_times[left] <= limit:
                total -= 1
                broker_bound -= group_flags[left]
                left += 1

            if total > 0:
                ratio[position] = broker_bound / total

        asymmetry[positions[start:end]] = ratio
        start = end

    return asymmetry


def _new_connection_features(work):
    """Pares de endpoints nuevos hacia el broker en los últimos 5 s."""
    size = len(work)
    result = np.zeros(size, dtype=float)

    order = work.sort_values(['capture_code', 't', 'pos'], kind='stable')
    positions = order['pos'].to_numpy()
    codes = order['capture_code'].to_numpy()
    times = order['t'].to_numpy(dtype=float)
    pairs = order['pair_code'].to_numpy()
    client_to_broker = order['is_client_to_broker'].to_numpy(dtype=float)

    start = 0
    while start < size:
        end = start + 1
        code = codes[start]
        while end < size and codes[end] == code:
            end += 1

        seen = set()
        first_seen = deque()
        for position in range(start, end):
            timestamp = times[position]
            limit = timestamp - WINDOW_SECONDS
            while first_seen and first_seen[0] <= limit:
                first_seen.popleft()
            result[positions[position]] = len(first_seen)

            if client_to_broker[position] > 0:
                pair = pairs[position]
                if pair not in seen:
                    seen.add(pair)
                    first_seen.append(timestamp)

        start = end

    return result


def build_tcp_features(df):
    """Matriz de la opción B, en el orden de `TCP_FEATURE_COLUMNS`."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError('build_tcp_features expects a pandas DataFrame')

    size = len(df)
    if size == 0:
        return pd.DataFrame(columns=TCP_FEATURE_COLUMNS, index=df.index, dtype=float)

    times = _numeric(df, 'frame.time_epoch').to_numpy(dtype=float)
    if not np.isfinite(times).all():
        raise ValueError('frame.time_epoch must be present and finite for every row')

    frame_len = _numeric(df, 'frame.len').fillna(0.0).to_numpy(dtype=float)
    source_port = _numeric(df, 'tcp.srcport').fillna(-1).astype(int).to_numpy()
    dest_port = _numeric(df, 'tcp.dstport').fillna(-1).astype(int).to_numpy()

    mqtt_port = np.isin(source_port, MQTT_PORTS) | np.isin(dest_port, MQTT_PORTS)
    broker_to_client = np.isin(source_port, MQTT_PORTS)
    client_to_broker = np.isin(dest_port, MQTT_PORTS)

    if '_direction' in df.columns:
        direction_values = list(df['_direction'])
    elif {'ip.src', 'ip.dst'} <= set(df.columns):
        direction_values = list(zip(
            df['ip.src'].astype(str), source_port,
            df['ip.dst'].astype(str), dest_port,
        ))
    else:
        direction_values = list(zip(source_port, dest_port))

    direction_codes = _factorize(direction_values)
    pair_codes = _factorize([_endpoint_pair(value) for value in direction_values])

    if '_capture' in df.columns:
        capture_values = list(df['_capture'])
    else:
        capture_values = ['capture'] * size
    capture_codes = _factorize(capture_values)

    if '_connection' in df.columns:
        connection_values = list(df['_connection'])
    else:
        connection_values = direction_values
    connection_codes = _factorize(connection_values)

    provided_delta = _numeric(df, 'frame.time_delta').to_numpy(dtype=float)
    computed_delta = _previous_delta(times, capture_codes)
    time_delta = np.where(np.isfinite(provided_delta), provided_delta, computed_delta)
    time_delta = np.where(np.isfinite(time_delta), time_delta, 0.0)
    time_delta = np.maximum(time_delta, 0.0)

    work = pd.DataFrame({
        'pos': np.arange(size, dtype=np.int64),
        'capture_code': capture_codes,
        'direction_code': direction_codes,
        'connection_code': connection_codes,
        'pair_code': pair_codes,
        't': times,
        'frame_len': frame_len,
        'is_client_to_broker': client_to_broker.astype(float),
    })
    work = work.sort_values(
        ['capture_code', 'direction_code', 't', 'pos'], kind='stable'
    ).reset_index(drop=True)

    iat, frames_5s, bytes_5s, len_std, iat_std = _direction_features(work)
    asymmetry = _connection_features(work)
    new_connections = _new_connection_features(work)

    result = pd.DataFrame(index=df.index)
    result['frame.len'] = frame_len
    result['fe_log_len'] = np.log1p(frame_len)
    result['frame.time_delta'] = time_delta
    result['fe_is_standard_mqtt_port'] = mqtt_port.astype(float)
    result['fe_is_broker_to_client'] = broker_to_client.astype(float)
    result['tcp_iat'] = iat
    result['tcp_iat_std_5s'] = iat_std
    result['tcp_frames_5s'] = frames_5s
    result['tcp_bytes_5s'] = bytes_5s
    result['tcp_len_std_5s'] = len_std
    result['tcp_asymmetry_5s'] = asymmetry
    result['tcp_new_conns_5s'] = new_connections

    result = result[TCP_FEATURE_COLUMNS]
    return result.replace([np.inf, -np.inf], 0.0).fillna(0.0)
