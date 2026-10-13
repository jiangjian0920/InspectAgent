FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import requests, dotenv, zai, langgraph; from zai import ZhipuAiClient; print('zai-sdk ok', getattr(zai, '__version__', 'unknown'))"

COPY main.py .
COPY agent ./agent
COPY tests ./tests

RUN chown -R appuser:appuser /app
USER 10001

ENTRYPOINT ["python", "main.py"]
CMD ["--check-config"]
