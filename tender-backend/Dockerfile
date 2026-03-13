FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first for layer caching
COPY pyproject.toml .
COPY README.md .

# Install dependencies
RUN uv pip install --system .

# Copy source code
COPY main.py .
COPY src/ src/
COPY templates/ templates/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
