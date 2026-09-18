"""IoT devices and payloads used for normal traffic."""

from __future__ import annotations

import random


class IoTDevice:
    """Periodic publisher definition for one simulated device."""
    def __init__(self, device_id, topic, payloads, interval, qos=0):
        """Configure identity, topic, payload choices, interval, and QoS."""
        self.id = device_id
        self.topic = topic
        self.payloads = payloads
        self.interval = interval
        self.qos = qos
        self.next_time = random.uniform(0.0, interval)

    def next_payload(self):
        """Choose the next payload from this device's configured values."""
        return str(random.choice(self.payloads))


def build_devices():
    """Return the default set of simulated home devices."""
    return [
        IoTDevice('sonar', 'distance/ultrasonic1', ['100', '150', '200', '352', '400'], 2.0),
        IoTDevice('relay', 'light/rele1', ['0', '1'], 3.0),
    ]
