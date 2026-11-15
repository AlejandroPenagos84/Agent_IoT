#!/bin/sh
# Certificados autofirmados de desarrollo/laboratorio. Idempotente: no pisa
# certificados existentes.
#
#   AGENT_CERT_DIR      CA propia + certificado del agente (puerto 8443).
#   MOSQUITTO_CERT_DIR  certificado del Mosquitto de laboratorio (MQTTS 8883).
set -eu
apk add --no-cache openssl >/dev/null

# Certificados de versiones anteriores (SAN "agente") no sirven para "app".
agent_cert_ok() {
  [ -f "$1/server.crt" ] && openssl x509 -in "$1/server.crt" -noout \
    -checkhost app 2>/dev/null | grep -q 'does match'
}

if [ -n "${AGENT_CERT_DIR:-}" ] && ! agent_cert_ok "$AGENT_CERT_DIR"; then
  d=$AGENT_CERT_DIR
  mkdir -p "$d"
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout "$d/ca.key" -out "$d/ca.crt" -subj "/CN=agentiot-ca" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
  openssl req -newkey rsa:2048 -nodes -subj "/CN=app" \
    -keyout "$d/server.key" -out "$d/server.csr"
  printf '%s\n' "basicConstraints=CA:FALSE" \
    "keyUsage=digitalSignature,keyEncipherment" \
    "extendedKeyUsage=serverAuth" \
    "subjectAltName=DNS:app,DNS:localhost,IP:127.0.0.1" > "$d/server.ext"
  openssl x509 -req -in "$d/server.csr" -CA "$d/ca.crt" -CAkey "$d/ca.key" \
    -CAcreateserial -days 3650 -extfile "$d/server.ext" -out "$d/server.crt"
  rm -f "$d/server.csr" "$d/server.ext" "$d/ca.srl"
  chmod 644 "$d/ca.crt" "$d/server.crt"
  chmod 600 "$d/ca.key" "$d/server.key"
  echo "certgen: agente listo en $d"
fi

if [ -n "${MOSQUITTO_CERT_DIR:-}" ] && [ ! -f "$MOSQUITTO_CERT_DIR/server.crt" ]; then
  d=$MOSQUITTO_CERT_DIR
  mkdir -p "$d"
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout "$d/server.key" -out "$d/server.crt" -subj "/CN=mosquitto" \
    -addext "subjectAltName=DNS:mosquitto,DNS:localhost,IP:127.0.0.1"
  cp "$d/server.crt" "$d/ca.crt"
  # Mosquitto corre con su propio usuario y debe poder leer la llave.
  chmod 644 "$d/server.key" "$d/server.crt" "$d/ca.crt"
  echo "certgen: mosquitto listo en $d"
fi
