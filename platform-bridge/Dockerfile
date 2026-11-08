FROM iot_assignment-tools:latest

WORKDIR /app

COPY . /app/platform-bridge

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8005

EXPOSE 8005

ENTRYPOINT ["uvicorn", "platform-bridge.app:app"]
CMD ["--host", "0.0.0.0", "--port", "8005"]
