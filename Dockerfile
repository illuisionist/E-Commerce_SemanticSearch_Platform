# Base image
FROM python:3.11-slim

# Avoid interactive debconf
ENV DEBIAN_FRONTEND=noninteractive

# Install small essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /app

# Copy only the files needed for building environment
COPY requirements.txt /app/requirements.txt
COPY scripts /app/scripts

# Install Python deps - try orjson/ujson but do not fail hard
RUN pip install --no-cache-dir -r /app/requirements.txt || pip install --no-cache-dir python-dateutil

# Make the script executable
RUN chmod +x /app/scripts/convert_meta_reviews.py

# Default command is help; users will override in docker-compose or CLI
ENTRYPOINT ["python", "/app/scripts/convert_meta_reviews.py"]
