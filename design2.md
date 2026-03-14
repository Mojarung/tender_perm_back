


Here is the complete, finalized System Architecture & Design Document. I have completed the cut-off Polars code, integrated the **Docker Compose** architecture using **uv**, and added strict directives for the AI Agent to utilize **MCP context7** for retrieving up-to-date documentation.

***

# SYSTEM ARCHITECTURE & DESIGN DOCUMENT (v2.0 - 2026 Standards)
**Project:** Tender Hack Perm - Intelligent NMCC Calculator (Human-in-the-Loop Pipeline)
**Target Audience:** AI Developer Agent
**Language:** English (Strict, highly detailed)

## 1. Executive Summary
This document outlines the architecture for an intelligent backend service designed to calculate and justify the Initial Maximum Contract Price (NMCC) based on hackathon rules. The system operates entirely offline (Linux server, no external APIs) using local open-weight models. It leverages **FastAPI**, a locally hosted **Qdrant** Vector DB, **Hugging Face** local embeddings (`perplexity-ai/pplx-embed-v1-0.6b`), **IsolationForest** for outlier detection, and **LangGraph** to implement an interruptible State Machine allowing manual user intervention at every critical step. High-performance data manipulation is strictly handled via **Polars** to ensure instant filtering and aggregations.

## 2. Technology Stack (2025-2026 Standards)
*   **Language:** Python 3.12+ (Utilizing native `|` union types, generic standard collections, and optimized runtime).
*   **Dependency Manager:** `uv` (by Astral) – Replaces Poetry/Pip for blazingly fast, deterministic resolution and virtual environment management.
*   **Web Framework:** `FastAPI` (with Pydantic V2 for strict, high-speed serialization/validation and Async Lifespan).
*   **Data Processing:** `Polars` – Utilized for multithreaded, memory-efficient eager/lazy dataframe operations on `contracts.json`.
*   **Embedding Model:** `perplexity-ai/pplx-embed-v1-0.6b` (Inferred locally via `sentence-transformers`, strictly offline).
*   **Vector Database:** `Qdrant` (Local Docker container).
*   **Workflow Engine:** `LangGraph` & `LangChain Core` (State Graph with `MemorySaver` for robust human-in-the-loop checkpoints).
*   **Machine Learning (Statistical):** `scikit-learn` (`IsolationForest` for anomaly/outlier detection).
*   **Document Generation:** `docxtpl` (Python-docx-template) and `Jinja2` for generating the `.docx` justification document.

## 3. Data Architecture & Preprocessing
The system relies on two static JSON datasets.

### 3.1. Datasets & Ingestion Strategy
1.  `cte.json`: Contains the catalog of items (CTE).
    *   *Action:* Embedded once upon initialization using `pplx-embed` and upserted into Qdrant.
2.  `contracts.json`: Contains historical contract data.
    *   *Action:* Loaded into memory using **Polars**. Given modern server RAM, `polars.read_json()` is used for extremely fast querying during the `process_prices` node.

### 3.2. Vector DB Schema (Qdrant)
*   **Collection Name:** `cte_catalog`
*   **Vector Configuration:** Standard float array (dimensions matching `pplx-embed-v1-0.6b` output), Cosine similarity.
*   **Payload:** `cte_id` (str), `name` (str), `category` (str), `attributes` (dict).

## 4. LangGraph State Machine (Human-in-the-Loop)
To satisfy the requirement of allowing the user to view, edit, and manually input prices or analogs, the core logic is modeled as a Directed State Graph using `LangGraph`.

### 4.1. Graph State Definition (`TypedDict` / Pydantic V2)
```python
from pydantic import BaseModel, Field
from typing import Any

class PipelineState(BaseModel):
    session_id: str
    target_cte_name: str
    region_filter: str | None = None
    
    # State 1: Analog Search
    retrieved_analogs: list[dict[str, Any]] = Field(default_factory=list)
    user_approved_analogs: list[dict[str, Any]] = Field(default_factory=list) 
    
    # State 2: Price Fetching & Filtering
    raw_prices: list[dict[str, Any]] = Field(default_factory=list)
    filtered_prices: list[dict[str, Any]] = Field(default_factory=list) 
    outlier_prices: list[dict[str, Any]] = Field(default_factory=list)
    user_approved_prices: list[dict[str, Any]] = Field(default_factory=list) 
    
    # State 3: Calculation
    calculated_median: float = 0.0
    final_nmcc_price: float = 0.0
    
    # State 4: Document
    document_url: str | None = None
    
    current_step: str = "init"
```

### 4.2. Graph Nodes & Edges
1.  **Node: `search_analogs`**: Embeds `target_cte_name`. Queries Qdrant. Halts and transitions to `wait_for_analog_approval`.
2.  **Node: `wait_for_analog_approval`**: Human node (receives modified analog list via API).
3.  **Node: `process_prices`**: Uses **Polars** to filter `contracts.json` by approved CTE IDs, dates, and regions. Applies `IsolationForest`. Halts and transitions to `wait_for_price_approval`.
4.  **Node: `wait_for_price_approval`**: Human node (receives manually verified prices/additions).
5.  **Node: `calculate_nmcc`**: Calculates the median and applies official mathematical formulas to determine range and final NMCC.
6.  **Node: `generate_document`**: Populates a `.docx` template using `docxtpl` and saves to disk.

## 5. Implementation Details (Polars & Outlier Logic)

### 5.1. Polars Data Access Singleton
Load the contract data once during the FastAPI lifespan.
```python
# src/data_access/polars_repo.py
import polars as pl
from pathlib import Path

class ContractRepository:
    _df: pl.DataFrame | None = None

    @classmethod
    def load_data(cls, file_path: Path) -> None:
        cls._df = pl.read_json(file_path)
        cls._df = cls._df.with_columns([
            pl.col("Дата заключения контракта").str.to_datetime("%Y-%m-%d %H:%M:%S.%f", strict=False),
            pl.col("Цена за единицу").cast(pl.Float64)
        ])

    @classmethod
    def get_prices_for_ctes(cls, cte_ids: list[str], region: str | None = None) -> pl.DataFrame:
        if cls._df is None:
            raise ValueError("Data not loaded")
        
        query = cls._df.filter(pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids))
        if region:
            query = query.filter(pl.col("Регион заказчика") == region)
        return query
```

### 5.2. Outlier Detection Logic (Polars + Sklearn Bridge)
Strict adherence to `IsolationForest` combined with Polars.
```python
# src/ml/stats.py
from sklearn.ensemble import IsolationForest
import polars as pl
import numpy as np

def remove_outliers_and_get_median(df_prices: pl.DataFrame) -> tuple[list[dict], list[dict], float]:
    """
    Expects a Polars DataFrame containing at least a 'Цена за единицу' column.
    """
    if df_prices.height < 3:
        median_val = df_prices.select(pl.col("Цена за единицу").median()).item()
        return df_prices.to_dicts(),[], float(median_val) if median_val else 0.0
    
    # Extract prices to numpy array for sklearn
    prices_array = df_prices.select("Цена за единицу").to_numpy()
    
    # Fit Isolation Forest
    clf = IsolationForest(random_state=42, contamination="auto")
    preds = clf.fit_predict(prices_array)
    
    # Add predictions back to Polars DataFrame
    df_with_preds = df_prices.with_columns(pl.Series(name="is_inlier", values=preds))
    
    # Split into valid and outliers
    valid_df = df_with_preds.filter(pl.col("is_inlier") == 1).drop("is_inlier")
    outliers_df = df_with_preds.filter(pl.col("is_inlier") == -1).drop("is_inlier")
    
    # Calculate median on valid data
    median_val = valid_df.select(pl.col("Цена за единицу").median()).item()
    
    return valid_df.to_dicts(), outliers_df.to_dicts(), float(median_val) if median_val else 0.0
```

## 6. Containerization & Deployment (Docker Compose & uv)
To meet the strict "offline Linux server" hackathon requirement, the solution is packaged using `docker-compose`. Dependency installation and application execution are strictly managed by `uv`.

### 6.1. Dockerfile
```dockerfile
# Dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential && rm -rf /var/lib/apt/lists/*

# Install uv (2026 standard)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Ensure uv works globally and sets up the system python environment
ENV UV_PROJECT_ENVIRONMENT=/usr/local

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv (Strictly offline-ready after this step)
RUN uv sync --no-dev --frozen

# Pre-download huggingface models so they are baked into the image (Offline requirement)
ENV HF_HOME=/app/.cache/huggingface
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('perplexity-ai/pplx-embed-v1-0.6b')"

# Enforce offline mode for runtime
ENV HF_DATASETS_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Copy project files
COPY . .

# Run the application via uv
CMD["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.2. docker-compose.yml
```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - EMBEDDING_MODEL_PATH=perplexity-ai/pplx-embed-v1-0.6b
      - TRANSFORMERS_OFFLINE=1
    volumes:
      - ./data:/app/data
      - ./templates:/app/templates
    depends_on:
      - qdrant

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_storage:/qdrant/storage

volumes:
  qdrant_storage:
```

## 7. Agent Directives & Documentation (MCP context7)

**CRITICAL INSTRUCTION FOR THE AI IMPLEMENTATION AGENT:**
Before generating the implementation code for this design document, you **MUST** utilize the Model Context Protocol (`mcp context7`) to retrieve the most up-to-date documentation and breaking changes for the following libraries (assuming 2025/2026 syntax):
1.  **Polars:** Use `mcp context7` to fetch documentation on Polars `pl.read_json()`, `LazyFrame` aggregations, and context expression syntax (`pl.col()`).
2.  **LangGraph:** Use `mcp context7` to fetch the latest compilation methods (`StateGraph`, `MemorySaver`, `END` transitions) as the LangChain ecosystem updates frequently.
3.  **FastAPI & Pydantic V2:** Use `mcp context7` to verify the usage of `@asynccontextmanager` for the lifespan model loading and `Pydantic` `Field` validations.
4.  **uv:** Use `mcp context7` to review astral-sh `uv` CLI commands (`uv sync`, `uv run`) to ensure the `Dockerfile` and setup instructions remain perfectly accurate.

*Do not rely on your pre-2024 training data for LangGraph and Polars API surfaces. Use `mcp context7` to guarantee syntactical correctness for the year 2026.*