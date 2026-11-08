


# Raw columns used directly by the model.
RAW_FEATURE_COLUMNS = [
    'frame.len', 'frame.time_delta', 'mqtt.hdrflags',
    'mqtt.len', 'mqtt.topic_len',
]

# Raw columns used to derive features without retaining their original values.
# Ports produce flags; text is summarized as entropy and topic depth.
DERIVED_PORT_COLUMNS = ['tcp.dstport', 'tcp.srcport']
DERIVED_TEXT_COLUMNS = ['mqtt.msg', 'mqtt.topic']

# Generated features retained for training.
# Network: byte rate, MQTT port flags, and log-scaled frame length.
ENGINEERED_NETWORK_COLUMNS = [
    'fe_bytes_per_sec', 'fe_is_standard_mqtt_port',
    'fe_is_broker_to_client', 'fe_log_len',
]
# MQTT: message/topic entropy, topic depth, and MQTT-to-frame length ratio.
ENGINEERED_MQTT_COLUMNS = [
    'fe_msg_entropy', 'fe_topic_entropy',
    'fe_topic_depth', 'fe_payload_ratio',
]
ENGINEERED_FEATURE_COLUMNS = [
    *ENGINEERED_NETWORK_COLUMNS, *ENGINEERED_MQTT_COLUMNS,
]

# Capture timestamps and frame order can leak capture-specific information.
DISCARD_CAPTURE_TIME_COLUMNS = [
    'frame.time_epoch', 'frame.time_relative', 'frame.number',
]
# Host, MAC, and client identifiers are context, not model features.
DISCARD_IDENTITY_COLUMNS = [
    'ip.src', 'ip.dst', 'eth.src', 'eth.dst', 'mqtt.clientid',
]
# MQTT fields already represented by mqtt.hdrflags.
DISCARD_DERIVABLE_COLUMNS = [
    'mqtt.msgtype', 'mqtt.qos', 'mqtt.retain', 'mqtt.dupflag',
]

# Target and grouping keys are not model features.
INTERNAL_COLUMNS = [
    'type', '_capture', '_original_row', '_endpoints', '_connection', '_direction',
]

# Final model matrix order; changing it requires retraining.
FEATURE_COLUMNS = [
    'frame.len', 'frame.time_delta',
    'fe_bytes_per_sec', 'fe_is_standard_mqtt_port', 'fe_is_broker_to_client', 'fe_log_len',
    'mqtt.hdrflags', 'mqtt.len', 'mqtt.topic_len',
    'fe_msg_entropy', 'fe_topic_entropy', 'fe_topic_depth', 'fe_payload_ratio',
]
assert len(FEATURE_COLUMNS) == 13
assert set(FEATURE_COLUMNS) == set(RAW_FEATURE_COLUMNS + ENGINEERED_FEATURE_COLUMNS)


def entropy(text):
    """Compute Shannon entropy for an optional text field."""
    import math
    from collections import Counter

    import pandas as pd

    if pd.isna(text) or not str(text):
        return 0.0
    text = str(text)
    probabilities = [count / len(text) for count in Counter(text).values()]
    return -sum(probability * math.log2(probability) for probability in probabilities)


def drop_identifier_columns(df):
    """Drop IP, MAC, and client_id after connection keys have been built."""
    present = [col for col in DISCARD_IDENTITY_COLUMNS if col in df.columns]
    return df.drop(columns=present)
