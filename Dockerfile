FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/usr/local

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

ENV HF_HOME=/app/.cache/huggingface
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('perplexity-ai/pplx-embed-v1-0.6b')"

ENV HF_DATASETS_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

COPY . .

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
