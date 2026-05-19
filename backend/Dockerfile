# ==========================================
# 🐍 Dockerfile — SAVIA FastAPI Backend
# ==========================================

FROM python:3.11-slim

WORKDIR /app

# Install system fonts for PDF Unicode support and PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py db_engine.py ai_engine.py auth.py config.py ./
COPY log_preprocessor.py s3_storage.py ./
COPY knowledge_base.xlsx ./
COPY logo-savia.png ./
COPY init-postgres.sh ./

# Make init script executable
RUN chmod +x /app/init-postgres.sh

# Create data directory for persistent volumes
RUN mkdir -p /app/data

# Environment variables
ENV PORT=8001
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

# Start with initialization script and uvicorn
CMD ["/bin/bash", "-c", "/app/init-postgres.sh && uvicorn main:app --host 0.0.0.0 --port 8001"]
