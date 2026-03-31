FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir redis minio requests

COPY worker-server.py /app/worker-server.py

CMD ["python3", "/app/worker-server.py"]
