FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for asyncpg / pgvector sometimes)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Command to run application is specified in docker-compose.yml
