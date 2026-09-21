FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tshark \
        tcpdump \
    && rm -rf /var/lib/apt/lists/*

COPY capture.sh /app/capture.sh
RUN chmod +x /app/capture.sh
WORKDIR /app

CMD ["./capture.sh"]
