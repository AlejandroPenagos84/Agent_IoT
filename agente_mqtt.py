from __future__ import annotations

import argparse
import sys

from factory import DEFAULT_TOPICS, AgentConfig, build_agent


def parse_args(argv=None) -> AgentConfig:
    ap = argparse.ArgumentParser(description='Agente detector MQTT (modelo híbrido)')
    ap.add_argument('--source', choices=['plaintext', 'tls'], default='plaintext')
    ap.add_argument('--model', choices=['hybrid', 'tls', 'case1', 'anomaly'],
                    default='hybrid')
    ap.add_argument('--modelos', dest='model_dir', default='/app/modelos_agente')
    ap.add_argument('--broker', dest='broker_host', default='localhost')
    ap.add_argument('--port', dest='broker_port', type=int, default=None)
    ap.add_argument('--topics', nargs='+', default=list(DEFAULT_TOPICS))
    ap.add_argument('--log', dest='registry_path', default=None)
    ap.add_argument('--no-registry-from-start', dest='registry_from_start',
                    action='store_false')
    ap.add_argument('--ca-certs', dest='ca_certs', default=None)
    ap.add_argument('--certfile', default=None)
    ap.add_argument('--keyfile', default=None)
    ap.add_argument('--insecure', action='store_true')
    ap.add_argument('--usuario', dest='username', default=None)
    ap.add_argument('--password', default=None)
    ap.add_argument('--ventana', dest='window_size', type=int, default=11)
    ap.add_argument('--cooldown', dest='alert_cooldown', type=float, default=2.0)
    ap.add_argument('--alert-port', dest='alert_port', type=int, default=1883)
    ap.add_argument('--alert-topic', dest='alert_topic', default='alertas/deteccion')
    ap.add_argument('--alert-file', dest='alert_file', default=None)
    ap.add_argument('--sin-reglas', dest='enable_intrusion_rules',
                    action='store_false')
    args = ap.parse_args(argv)
    return AgentConfig(**vars(args))


def main(argv=None) -> int:
    cfg = parse_args(argv)
    agent = build_agent(cfg)
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
