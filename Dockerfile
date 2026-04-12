# ==========================================
# 🐳 Dockerfile — SIC Terrain API + PWA
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements-pwa.txt .
RUN pip install --no-cache-dir -r requirements-pwa.txt

# Copy application files
COPY api_server.py db_engine.py auth.py config.py ./
COPY pwa-terrain/ ./pwa-terrain/

# Create data directory for SQLite
RUN mkdir -p /app/data

# Environment variables
ENV PORT=5000
ENV JWT_SECRET=sic-terrain-docker-secret-key
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Start with gunicorn
CMD ["gunicorn", "api_server:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120"]
