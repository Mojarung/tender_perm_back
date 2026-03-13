FROM python:3.12-slim

WORKDIR /app

# System dependencies for llama-cpp-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies
RUN uv pip install --system .

# Copy source code
COPY main.py .
COPY config.py .
COPY services/ services/
COPY download_models.py .
COPY export_onnx.py .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
