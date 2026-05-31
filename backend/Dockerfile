# ==========================================
# 🐍 Dockerfile — SAVIA FastAPI Backend
# ==========================================

FROM python:3.11-slim

WORKDIR /app

# Install system fonts for PDF Unicode support
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create data directory for persistent volumes
RUN mkdir -p /app/data

# Environment variables
ENV PORT=8001
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

# Start with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
