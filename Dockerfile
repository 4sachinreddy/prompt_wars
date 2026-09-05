# MedLens - Google Cloud Run Production Dockerfile
FROM python:3.11-slim

# Prevent Python from writing .pyc files & enable unbuffered standard I/O
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install system dependencies (needed for PDF rendering & build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and sample data
COPY app/ ./app/
COPY sample_data/ ./sample_data/

# Cloud Run binds to port 8080 by default
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Start FastAPI application with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
