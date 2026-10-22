# Data preprocessing

- `load_data.py` reads captures, normalizes labels, selects IPv4/TCP frames, and builds connection keys. `load_and_merge(files, normal_only=[...])` keeps only the `normal` frames of the listed captures (used for MitM and Intrusion); their attack frames are discarded, not relabeled.
- `feature_engineering.py` defines the model feature catalog and `drop_identifier_columns(df)` (no longer called by the notebook; `column_policy` drops identifiers).
- `mqtt_features.py` builds the 13-feature option A matrix (`build_feature_matrix`). It is kept only as the experimental reference for `02_tcp_vs_mqtt.ipynb`; the final model uses `tcp_features.py`.
- `tcp_features.py` defines `TCP_FEATURE_COLUMNS` and `build_tcp_features(df)`: the TCP/IP-only feature set (option B) used by section 2.9. Every window is causal (5 s, current frame excluded, 0 without history); IPs, ports and timestamps are only grouping/order keys. It reads `_connection`, `_direction` and `_capture` from `load_data`, so it must run after those keys exist. The notebook compares it against the current 13 MQTT features (option A).
- `column_policy.py` holds `SEMANTICS` (meaning of every captured column) and `build_column_policy(df)`, which returns the table `columna | semántica | motivo | acción | justificación frente a DoS` plus the evidence tables. It fails if a column has no documented semantics or a REDUNDANT claim does not hold. `apply_column_policy(df, policy, keep_context)` drops DROP columns except the context ones (`frame.time_epoch`).
- `eda/` measures and plots; it never decides. One folder per key point, each with `analysis.py` (tables) and/or `plots.py` (figures). Everything is re-exported from `eda/__init__.py`, so `eda.<function>` works.

| Folder | Functions |
|---|---|
| `common.py` | Constants, `packet_types` (type from `mqtt.hdrflags` bits 7-4), `parse_hdrflags`, shared helpers. |
| `missingness/` | `missingness_report`, `plot_missingness(report, policy=None)` |
| `packets_by_class/` | `packet_type_by_class`, `plot_packet_type_by_class` |
| `port_roles/` | `port_role_by_class`, `plot_port_role_by_class` |
| `duplicates/` | `duplicate_columns` |
| `redundancy/` | `HDRFLAGS_FIELDS`, `hdrflags_redundancy` (DUP/QoS/RETAIN checked only on PUBLISH) |
| `structural_nulls/` | `structural_null_alignment` (step 1), `packet_type_separation` (step 2), `plot_structural_presence`, `plot_packet_separation` |
| `connection_share/` | `connection_packet_share`, `plot_connection_packet_share` |
| `value_distributions/` | `values_by_class`, `plot_values_by_class` |
| `policy_summary/` | `plot_policy_summary` |
| `mqtt_proxy/` | `mqtt_proxy_table`, `trivial_rule_baseline`, `plot_mqtt_proxy` (2.3.1 ¿MQTT = DoS?) |
| `normal_by_capture/` | `normal_profile_by_capture`, `normal_packet_types_by_capture`, `port_rule_by_scope`, `plot_normal_by_capture` (2.3.2) |
| `capture_similarity/` | `numeric_summary_by_capture`, `ks_by_capture_pair`, `js_by_capture_pair`, `top_service_ports`, `host_overlap`, `origin_classifier`, `plot_capture_similarity` (2.3.3) |
| `temporal_concurrency/` | `attack_window`, `temporal_table`, `concurrent_normal_share`, `plot_temporal_concurrency` (2.3.4) |

`artifacts.py` (outside `eda/`, it does I/O): `save_clean_artifact(df, dir, manifest_kwargs)` validates `df_raw`, writes `df_raw.joblib`, reloads it to check the `_connection`/`_direction` tuples, and writes `manifest.json`. `load_clean_artifact(dir)` returns `(df_raw, manifest)` and fails if the SHA-256 or shape does not match; notebooks 02/03 use it.

Missingness never drives a decision. Motives: `EMPTY`, `CONSTANT`, `DUPLICATE`, `REDUNDANT`, `LEAKAGE`, `STRUCTURAL_NULL`, `RAW_TEXT`, `BEHAVIOR` (kept as is); actions: `DROP`, `KEEP`, `DERIVE`.

In the notebook, section 2 analyzes `df_captured` (the unfiltered load) and section 2.7 creates the filtered `df_raw`, so section 2 can be rerun without reloading the CSV.
