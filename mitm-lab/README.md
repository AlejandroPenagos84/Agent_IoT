# Laboratorio local de MitM (ARP spoofing) con Docker

Simula, en tu propia máquina, el patrón que parece producir la clase `mitm`
del dataset MQTT_UAD: un sensor IoT publicando por MQTT normalmente,
mientras un tercer contenedor hace ARP spoofing entre el sensor y el broker.

**Uso exclusivo en tu propia red Docker aislada.** No apuntes `IOT_IP` /
`BROKER_IP` en `attacker/mitm.sh` a nada fuera de la red `lab_net` definida
en `docker-compose.yml`. Hacer ARP spoofing sobre una red que no es tuya
(la wifi de tu casa compartida, una red de oficina, etc.) es ilegal en la
mayoría de jurisdicciones y puede tumbar el internet de otras personas.

## Estructura

```
mitm-lab/
├── docker-compose.yml
├── mosquitto.conf
├── iot/
│   ├── Dockerfile
│   └── publisher.py       # sensor MQTT normal, sin cambios
├── attacker/
│   ├── Dockerfile
│   └── mitm.sh             # arpspoof en ambos sentidos + ip_forward
├── capture/
│   ├── Dockerfile
│   └── capture.sh          # tshark sin filtro, comparte red con attacker
└── pcaps/                   # se crea sola, aquí caen las capturas
```

## Levantar el laboratorio

```bash
cd mitm-lab
docker compose up --build
```

Verás en los logs:
- `lab_iot` publicando temperatura cada 2 segundos.
- `lab_attacker` esperando a que respondan iot/broker y luego lanzando
  los dos `arpspoof`.
- `lab_capture` escribiendo el pcap en `./pcaps/`.

## Cómo saber que el ataque funcionó

Desde otra terminal, entra al contenedor del IoT y revisa su tabla ARP:

```bash
docker exec -it lab_iot sh -c "apt-get update && apt-get install -y iproute2 >/dev/null && ip neigh"
```

Antes del ataque, la IP del broker (`172.28.0.10`) apunta a su MAC real.
Unos segundos después de que `lab_attacker` arranque, esa misma IP debería
apuntar a la MAC del contenedor `lab_attacker`. Ese cambio es la evidencia
del spoofing.

También puedes abrir el pcap en Wireshark y filtrar por `arp`: deberías ver
ráfagas de respuestas ARP no solicitadas (`is-at`) enviadas repetidamente
por la MAC del atacante, alternando entre la IP del IoT y la del broker.

## Parar el laboratorio

```bash
docker compose down
```

Esto detiene el spoofing (el `trap` en `mitm.sh` mata los `arpspoof`) y dado
que `ip_forward` vive dentro del contenedor, no queda ningún rastro en tu
máquina anfitriona.

## De pcap a CSV estilo MQTT_UAD

El notebook trabaja con CSV, no con pcap. Para exportar columnas similares
a las que usa `load_and_merge` (no idénticas: el dataset original tiene 67
columnas y aquí solo tendrás las que tu tráfico realmente genere):

```bash
tshark -r pcaps/lab_XXXXXXXX_XXXXXX.pcap -T fields \
  -e frame.time_epoch -e frame.time_delta -e frame.time_delta_displayed \
  -e frame.len -e frame.cap_len \
  -e eth.src -e eth.dst \
  -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport \
  -e mqtt.msgtype -e mqtt.hdrflags -e mqtt.len -e mqtt.msg -e mqtt.topic \
  -E header=y -E separator=, -E quote=d \
  > mi_captura.csv
```

Tendrás que añadir tú mismo la columna `type` (`normal`/`mitm`) según el
rango de tiempo en que estuvo activo `lab_attacker`, igual que hizo
probablemente el dataset original. Esto es solo para explorar y entender
el ataque; no reemplaza ni debe mezclarse con `data/DoS.csv`,
`data/MitM.csv` ni `data/Intrusion.csv` del proyecto principal.

## Limitaciones de este lab frente al dataset real

- Aquí solo hay un sensor y un broker; el dataset mezcla muchos más
  dispositivos, así que sus ráfagas y su tabla ARP son más ricas.
- `arpspoof` de `dsniff` es una herramienta simple; el dataset pudo usar
  `ettercap`, `bettercap` u otra, con un patrón de ráfaga distinto.
- No hay tráfico "de fondo" (portátiles navegando) como en el testbed real.

Ninguna de estas diferencias invalida el ejercicio: el objetivo es que veas
con tus propios ojos por qué las filas `mitm` casi no tienen `ip.src` ni
puertos TCP, y por qué llegan en ráfagas hacia broadcast.
