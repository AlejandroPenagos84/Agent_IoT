FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        dsniff \
        iproute2 \
        procps \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY mitm.sh /app/mitm.sh
RUN chmod +x /app/mitm.sh
WORKDIR /app

CMD ["./mitm.sh"]
