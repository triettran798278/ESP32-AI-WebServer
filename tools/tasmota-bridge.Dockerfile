FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY virtual_tasmota.py tasmota_bridge.py /app/tools/
CMD ["python", "-u", "-m", "tools.tasmota_bridge"]
