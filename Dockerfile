FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY config ./config
RUN python -m pip install --upgrade pip && python -m pip install .

RUN mkdir -p /data/backups && chown -R appuser:appuser /data
USER appuser

EXPOSE 8091
CMD ["python", "-m", "hcm_invite_tracker"]
