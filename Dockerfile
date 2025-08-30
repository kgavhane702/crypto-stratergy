# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system deps (if any needed later, can extend)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first for better caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src ./src
COPY runner.py ./
COPY README.md ./
# Optionally copy env.txt template; real secrets should be mounted at runtime
COPY env.txt ./env.txt

# Create data and exports directories
RUN mkdir -p /app/data /app/exports && chmod 755 /app/data /app/exports

# Use src layout without install
ENV PYTHONPATH=/app/src

# Default command: run the monitor
CMD ["python", "runner.py"]
