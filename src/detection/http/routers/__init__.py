"""HTTP routers grouped by resource."""

from . import alerts, brokers, health, reports, sensors

__all__ = ["alerts", "brokers", "health", "reports", "sensors"]
