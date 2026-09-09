FROM python:3.11-slim

RUN useradd -m trader
WORKDIR /home/trader/app

RUN apt-get update && apt-get install -y \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY ibkr_core/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir prometheus-client

COPY ibkr_core/ ./ibkr_core/
COPY alembic.ini ./

RUN mkdir -p /home/trader/app/ibkr_core/data/models
RUN chown -R trader:trader /home/trader/app
USER trader

ENV PYTHONPATH=/home/trader/app
ENV IBKR_HOST=127.0.0.1
ENV IBKR_PORT=4002
# Fail-closed: require explicit DEV_MODE=true for development
ENV DEV_MODE=false

EXPOSE 8000
# Healthcheck uses /api/system/health (consistent with docker-compose.yml)
HEALTHCHECK --interval=30s --timeout=10s --retries=5 --start-period=60s \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

CMD ["uvicorn", "ibkr_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
