FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=4

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt setup.py setup.cfg MANIFEST.in ./
COPY piper ./piper

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . fastapi "uvicorn[standard]"

COPY server.py ./

EXPOSE 10200

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "10200"]
