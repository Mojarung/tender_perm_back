FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies if any are still needed, else just base packages
RUN apt-get update && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8001

# Command to run application is specified in docker-compose.yml
