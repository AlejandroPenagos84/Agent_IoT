FROM python:3.11-slim

RUN pip install --no-cache-dir paho-mqtt==1.6.1

COPY publisher.py /app/publisher.py
WORKDIR /app

CMD ["python", "publisher.py"]
