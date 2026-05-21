# ── Frontend Build Stage ──────────────────────────────────────────────────────
FROM oven/bun:latest as frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install
COPY frontend/ ./
RUN bun run build

# ── Backend & Production Stage ───────────────────────────────────────────────
FROM python:3.11-slim as runtime

# Security: Don't run as root
RUN useradd -m trader
WORKDIR /home/trader/app

# Install system dependencies for psycopg2 and other libs
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY ibkr_core/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir prometheus-client

# Copy application code
COPY ibkr_core/ ./ibkr_core/
COPY alembic.ini ./

# Create data directory for SQLite
RUN mkdir -p /home/trader/app/ibkr_core/data

# Copy frontend build from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set permissions
RUN chown -R trader:trader /home/trader/app
USER trader

# Default environment variables
ENV PYTHONPATH=/home/trader/app
ENV IBKR_HOST=127.0.0.1
ENV IBKR_PORT=4002

EXPOSE 8000

CMD ["uvicorn", "ibkr_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
