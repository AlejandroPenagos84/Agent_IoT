"""EDA de las columnas capturadas para la detección binaria DoS vs normal.

Una subcarpeta por punto clave; cada una separa ``analysis`` (tablas) de
``plots`` (gráficas). Las funciones miden y grafican, no deciden: las
decisiones viven en ``column_policy``. Todas reciben el DataFrame de
``load_and_merge``. Se re-exportan aquí para usar ``eda.<función>``.

- ``missingness``: nulos por columna.
- ``packets_by_class``: tipos de paquete MQTT por clase.
- ``port_roles``: rol del puerto 1883/8883 por clase.
- ``duplicates``: columnas idénticas (DUPLICATE).
- ``redundancy``: columnas derivables de mqtt.hdrflags (REDUNDANT).
- ``structural_nulls``: pasos 1 y 2 de STRUCTURAL_NULL.
- ``connection_share``: tipos de paquete por conexión.
- ``value_distributions``: valores observados por clase.
- ``policy_summary``: resumen de la tabla de política.
- ``mqtt_proxy``: ¿MQTT = DoS? composición por grupo y reglas triviales.
- ``normal_by_capture``: perfil del normal por captura de origen.
- ``capture_similarity``: ¿el normal de las capturas es el mismo?
- ``temporal_concurrency``: normal antes/durante/después del ataque.
"""

from .common import (
    MALFORMED, MQTT_ANY, MQTT_PACKET_TYPES, MQTT_PORTS, NO_MQTT, NORMAL_LABEL,
    TARGET_COL, mqtt_port_masks, normal_frames, packet_types, parse_hdrflags, port_role,
)
from .capture_similarity import (
    host_overlap, js_by_capture_pair, ks_by_capture_pair, numeric_summary_by_capture,
    origin_classifier, plot_capture_similarity, top_service_ports,
)
from .connection_share import connection_packet_share, plot_connection_packet_share
from .duplicates import duplicate_columns
from .missingness import missingness_report, plot_missingness
from .mqtt_proxy import mqtt_proxy_table, plot_mqtt_proxy, trivial_rule_baseline
from .normal_by_capture import (
    normal_packet_types_by_capture, normal_profile_by_capture, plot_normal_by_capture,
    port_rule_by_scope,
)
from .packets_by_class import packet_type_by_class, plot_packet_type_by_class
from .policy_summary import plot_policy_summary
from .port_roles import plot_port_role_by_class, port_role_by_class
from .redundancy import HDRFLAGS_FIELDS, hdrflags_redundancy
from .structural_nulls import (
    packet_type_separation, plot_packet_separation, plot_structural_presence,
    structural_null_alignment,
)
from .temporal_concurrency import (
    attack_window, concurrent_normal_share, plot_temporal_concurrency, temporal_table,
)
from .value_distributions import plot_values_by_class, values_by_class
