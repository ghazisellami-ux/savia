# ==========================================
# 🐍 Dockerfile — SAVIA FastAPI Backend
# ==========================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by PDF generation.
RUN apt-get update && apt-get install -y --no-install-recommends curl fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

# Install dependencies with retries, extended timeout, and alternative index
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --default-timeout=180 \
    --retries 10 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt || \
    pip install --no-cache-dir \
    --default-timeout=180 \
    --retries 10 \
    -r requirements.txt

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
