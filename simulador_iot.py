"""Backward-compatible entry point; implementation lives in ``simulation``."""

from simulation.cli import main, parse_args
from simulation.devices import IoTDevice, build_devices
from simulation.publishers import DryPublisher, MqttPublisher
from simulation.simulator import Simulator


if __name__ == "__main__":
    raise SystemExit(main())
