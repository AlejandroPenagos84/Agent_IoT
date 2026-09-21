"""
Simula un sensor IoT publicando lecturas de temperatura por MQTT.
No sabe ni necesita saber que está siendo interceptado: esto es
justo el punto del MitM, la víctima se comporta con normalidad.
"""
import random
import time

import paho.mqtt.client as mqtt

BROKER_HOST = "172.28.0.10"
BROKER_PORT = 1883
TOPIC = "sensores/temperatura"
CLIENT_ID = "sensor-temp-01"


def esperar_broker(client, intentos=15, espera_seg=2):
    for intento in range(1, intentos + 1):
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
            print(f"[iot] conectado al broker en el intento {intento}")
            return
        except Exception as exc:
            print(f"[iot] intento {intento}/{intentos} fallo: {exc}")
            time.sleep(espera_seg)
    raise RuntimeError("no se pudo conectar al broker")


def main():
    client = mqtt.Client(client_id=CLIENT_ID)
    esperar_broker(client)
    client.loop_start()

    while True:
        temperatura = round(random.uniform(20.0, 25.0), 2)
        payload = f"{temperatura}"
        client.publish(TOPIC, payload, qos=0)
        print(f"[iot] publicado {TOPIC} = {payload}")
        time.sleep(2)


if __name__ == "__main__":
    main()
