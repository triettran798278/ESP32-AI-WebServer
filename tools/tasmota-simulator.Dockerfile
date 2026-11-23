FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY virtual_tasmota.py /app/virtual_tasmota.py
CMD ["python", "-u", "/app/virtual_tasmota.py"]
