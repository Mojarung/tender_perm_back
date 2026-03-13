FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (build tools needed for some python packages like llama-cpp-python)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
# Setting extra CMAKE_ARGS to ensure compilation is optimized for CPU
ENV CMAKE_ARGS="-DGGML_NATIVE=ON"
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8001

# Command to run application is specified in docker-compose.yml
