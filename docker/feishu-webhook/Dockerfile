FROM python:3.12-slim

WORKDIR /app
COPY app.py .

RUN useradd --no-create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV ADAPTER_PORT=9095
EXPOSE 9095

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${ADAPTER_PORT}/healthz', timeout=3)"

CMD ["python", "app.py"]
