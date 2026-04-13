# ==========================================
# 🐳 Dockerfile — SAVIA FastAPI Backend
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Install dependencies (from freeze)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py db_engine.py ai_engine.py auth.py config.py ./
COPY views/ ./views/

# Create data directory for SQLite
RUN mkdir -p /app/data

# Environment variables
ENV PORT=8000
ENV JWT_SECRET=savia-super-secret-key-2026
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Start with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
