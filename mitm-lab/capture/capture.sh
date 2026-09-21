#!/bin/sh
set -e

mkdir -p /pcaps
PCAP_FILE="/pcaps/lab_$(date +%Y%m%d_%H%M%S).pcap"

echo "[capture] esperando a que exista la interfaz eth0"
sleep 5

echo "[capture] capturando en eth0 -> $PCAP_FILE"
echo "[capture] deten con Ctrl+C o 'docker compose stop capture'"

# --filter "" equivalente: sin filtro de captura, se ve todo (IP, ARP, etc.)
tshark -i eth0 -w "$PCAP_FILE"
