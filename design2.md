# SYSTEM ARCHITECTURE & DESIGN DOCUMENT (v3.0 — 2026 Standards)
**Project:** Tender Hack Perm — Intelligent NMCC Calculator (Human-in-the-Loop Pipeline)
**Target Audience:** AI Developer Agent
**Language:** English (Strict, highly detailed)

## 1. Executive Summary
This document outlines the architecture for an intelligent backend service designed to calculate and justify the Initial Maximum Contract Price (НМЦК — Начальная Максимальная Цена Контракта) based on hackathon rules. The system operates entirely offline (Linux server, no external APIs) using local open-weight models. It leverages **FastAPI**, a locally hosted **Qdrant** Vector DB with hybrid search (vector + category/attribute filters), **Hugging Face** local embeddings (`perplexity-ai/pplx-embed-v1-0.6b` via ONNX Runtime), **IsolationForest** for outlier detection, coefficient of variation validation, VAT normalization, time-weighted pricing, and **LangGraph** to implement an interruptible State Machine allowing manual user intervention at every critical step. High-performance data manipulation is strictly handled via **Polars**.

## 2. Technology Stack (2025-2026 Standards)
*   **Language:** Python 3.12+ (Utilizing native `|` union types, generic standard collections, and optimized runtime).
*   **Dependency Manager:** `uv` (by Astral) – Replaces Poetry/Pip for blazingly fast, deterministic resolution and virtual environment management.
*   **Web Framework:** `FastAPI` (with Pydantic V2 for strict, high-speed serialization/validation and Async Lifespan).
*   **Data Processing:** `Polars` – Utilized for multithreaded, memory-efficient eager/lazy dataframe operations on `contracts.json`.
*   **Embedding Model:** `perplexity-ai/pplx-embed-v1-0.6b` (Inferred locally via **ONNX Runtime** for speed; dimension = **1024**, cosine similarity, no instruction prefix needed).
*   **Vector Database:** `Qdrant` (Local Docker container, with **payload filtering** for hybrid search).
*   **Workflow Engine:** `LangGraph` & `LangChain Core` (State Graph with `MemorySaver` for robust human-in-the-loop checkpoints).
*   **Machine Learning (Statistical):** `scikit-learn` (`IsolationForest` for anomaly/outlier detection).
*   **Document Generation:** `docxtpl` (Python-docx-template) and `Jinja2` for generating the `.docx` justification document.
*   **Frontend:** Minimal web UI (React/Vite or plain HTML+JS) — required by hackathon ТЗ.

## 3. Data Architecture & Preprocessing
The system relies on two static JSON datasets.

### 3.1. Dataset Schemas (Actual Fields)

#### 3.1.1. `cte.json` — CTE Catalog (~350 MB)
Array of objects. Each entry:
```json
{
  "Идентификатор СТЕ": 34863000,           // int — unique CTE ID
  "Наименование СТЕ": "Мусорные пакеты 35л", // str — item name
  "Категория": "Пакеты полимерные",          // str — category (CRITICAL for filtering)
  "Производитель": "ООО СПРИНТ-ПЛАСТ",       // str — manufacturer
  "характеристики СТЕ": [                    // array of [key, value] pairs
    ["Количество в упаковке", "30.00000"],
    ["Толщина, мкм", "50.00000"],
    ["Объем", "35.00000"],
    ["Цвет", "черный"],
    ["Вид материала", "ПВД"]
  ]
}
```

#### 3.1.2. `contracts.json` — Historical Contracts (~560 MB)
Array of objects. Each entry:
```json
{
  "Наименование закупки": "Поставка кухонного бытового оборудования...",
  "Количество": 1.0,                                    // float — quantity
  "Единица измерения": "шт",                             // str — unit of measure
  "Идентификатор контракта": 204746787,                  // int — contract ID
  "Способ закупки": "Контракт по итогам котировочной сессии",
  "Начальная стоимость контракта": 71091.9,              // float — initial contract price
  "Стоимость контракта после заключения": 71091.9,       // float — final contract price
  "% снижения": 0.0,                                    // float — discount percentage
  "Ставка НДС": "20%",                                  // str — VAT rate ("20%", "10%", "Без НДС")
  "Дата заключения контракта": "2025-12-01 14:32:09.307",// str — contract date
  "ИНН заказчика": 9718159964,                           // int — buyer TIN
  "Регион заказчика": "Москва",                          // str — buyer region
  "ИНН поставщика": 7729101722,                          // int — supplier TIN
  "Регион поставщика": "Москва",                         // str — supplier region
  "Идентификатор СТЕ по контракту": 35927039,            // int — CTE ID (JOIN key to cte.json)
  "Наименование позиции СТЕ": "Холодильник Haier MSR115 белый", // str — item name in contract
  "Цена за единицу": 23760.0                             // float — unit price
}
```

### 3.2. Ingestion Strategy
1.  `cte.json`:
    *   Load via `json.load()` + `pl.DataFrame()` (Polars cannot directly parse nested arrays-of-arrays).
    *   Preprocess: convert `характеристики СТЕ` from `list[list[str, str]]` to `dict[str, str]` for payload storage.
    *   Build embedding text: concatenate `Наименование СТЕ` + `Категория` + key characteristics.
    *   Embed using `pplx-embed-v1-0.6b` (ONNX) → 1024-dim vectors
    *   Upsert into Qdrant with vector + payload.

2.  `contracts.json`:
    *   Load via `json.load()` + `pl.DataFrame()` (safe for ~560 MB, more reliable than `pl.read_json` for JSON arrays).
    *   Parse dates: `pl.col("Дата заключения контракта").str.to_datetime("%Y-%m-%d %H:%M:%S%.f", strict=False)`
    *   Cast types: `Цена за единицу → Float64`, `Количество → Float64`
    *   Normalize VAT (see §5.3).

### 3.3. Vector DB Schema (Qdrant)
*   **Collection Name:** `cte_catalog`
*   **Vector Configuration:** Dense, dimension = **1024**, distance = **Cosine**.
*   **Payload Fields (indexed for filtering):**

| Payload Field | Source Field | Type | Indexed |
|---|---|---|---|
| `cte_id` | `Идентификатор СТЕ` (cast to str) | `keyword` | ✅ |
| `name` | `Наименование СТЕ` | `text` | ✅ |
| `category` | `Категория` | `keyword` | ✅ — **critical for hybrid search** |
| `manufacturer` | `Производитель` | `keyword` | ✅ |
| `attributes` | `характеристики СТЕ` → `dict` | `json` | ❌ (used post-retrieval) |

**Embedding Text Construction:**
```python
def build_embedding_text(item: dict) -> str:
    """Concatenate name + category + top attributes for richer embedding."""
    parts = [item["Наименование СТЕ"], item["Категория"]]
    for key, val in item["attributes"].items():
        parts.append(f"{key}: {val}")
    return " | ".join(parts)
```

## 4. Hybrid Search Strategy (Vector + Filter)

### 4.1. Why Hybrid Search is Required
The hackathon ТЗ explicitly states: *"поиск сопоставимых товарных позиций по названию, **характеристикам и категориям** справочника"*.

Pure vector search fails on:
- Technical specifications: cable "3×2.5" vs "3×1.5" → high cosine but different prices
- Volume/size differences: "Мусорные пакеты 35л" vs "240л" → ~95% similarity but 3× price difference
- Cross-category matches: embedding may rank "Холодильник" near "Морозильник" even with wildly different categories

### 4.2. Search Pipeline
```
User input (CTE name)
    │
    ▼
Step 1: Embed query text → 1024-dim vector
    │
    ▼
Step 2: Qdrant search with CATEGORY FILTER (if known)
    │  query_filter = models.Filter(must=[
    │      models.FieldCondition(key="category", match=models.MatchValue(value=category))
    │  ])
    │  Top-K results (K=20), score_threshold=0.65
    │
    ▼
Step 3: Post-retrieval ranking by attribute overlap
    │  For each result, compute attribute_match_score:
    │    - Count matching characteristic keys and values
    │    - Weight: exact value match > key-only match
    │  final_score = 0.6 * cosine_score + 0.4 * attribute_match_score
    │
    ▼
Step 4: Return top-N (N=10) ranked analogs → User review
```

## 5. Implementation Details

### 5.1. Polars Data Access Singleton
```python
# src/data_access/polars_repo.py
import polars as pl
import json
from pathlib import Path

class ContractRepository:
    _df: pl.DataFrame | None = None

    @classmethod
    def load_data(cls, file_path: Path) -> None:
        """Load contracts.json safely for large JSON arrays."""
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cls._df = pl.DataFrame(raw)
        cls._df = cls._df.with_columns([
            pl.col("Дата заключения контракта")
              .str.to_datetime("%Y-%m-%d %H:%M:%S%.f", strict=False)
              .alias("Дата заключения контракта"),
            pl.col("Цена за единицу").cast(pl.Float64),
            pl.col("Количество").cast(pl.Float64),
        ])

    @classmethod
    def get_prices_for_ctes(
        cls,
        cte_ids: list[int],
        region: str | None = None,
        months_back: int = 12,
    ) -> pl.DataFrame:
        """Filter contracts by CTE IDs, region, and date freshness."""
        if cls._df is None:
            raise ValueError("Data not loaded")

        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=months_back * 30)

        query = cls._df.filter(
            pl.col("Идентификатор СТЕ по контракту").is_in(cte_ids)
            & (pl.col("Дата заключения контракта") >= cutoff)
        )
        if region:
            query = query.filter(pl.col("Регион заказчика") == region)
        return query
```

### 5.2. Outlier Detection + Coefficient of Variation
```python
# src/ml/stats.py
from sklearn.ensemble import IsolationForest
import polars as pl
import numpy as np

class PriceAnalysisResult:
    valid_prices: list[dict]
    outlier_prices: list[dict]
    median: float
    mean: float
    coefficient_of_variation: float  # MUST be ≤ 33% for valid NMCK
    is_homogeneous: bool             # True if CV ≤ 33%

def analyze_prices(df_prices: pl.DataFrame) -> PriceAnalysisResult:
    """
    1. Normalize VAT to common base (without VAT)
    2. Apply IsolationForest to remove outliers
    3. Calculate coefficient of variation
    4. Return structured result with homogeneity flag
    """
    # Step 1: Normalize VAT
    df_normalized = normalize_vat(df_prices)

    prices_col = "Цена за единицу (без НДС)"

    if df_normalized.height < 3:
        median_val = df_normalized.select(pl.col(prices_col).median()).item()
        mean_val = df_normalized.select(pl.col(prices_col).mean()).item()
        return PriceAnalysisResult(
            valid_prices=df_normalized.to_dicts(),
            outlier_prices=[],
            median=float(median_val or 0),
            mean=float(mean_val or 0),
            coefficient_of_variation=0.0,
            is_homogeneous=True,
        )

    # Step 2: IsolationForest outlier removal
    prices_array = df_normalized.select(prices_col).to_numpy()
    clf = IsolationForest(random_state=42, contamination="auto")
    preds = clf.fit_predict(prices_array)

    df_with_preds = df_normalized.with_columns(
        pl.Series(name="is_inlier", values=preds)
    )
    valid_df = df_with_preds.filter(pl.col("is_inlier") == 1).drop("is_inlier")
    outliers_df = df_with_preds.filter(pl.col("is_inlier") == -1).drop("is_inlier")

    # Step 3: Statistics on valid prices
    median_val = valid_df.select(pl.col(prices_col).median()).item()
    mean_val = valid_df.select(pl.col(prices_col).mean()).item()
    std_val = valid_df.select(pl.col(prices_col).std()).item()

    cv = (std_val / mean_val * 100) if mean_val and mean_val > 0 else 0.0

    return PriceAnalysisResult(
        valid_prices=valid_df.to_dicts(),
        outlier_prices=outliers_df.to_dicts(),
        median=float(median_val or 0),
        mean=float(mean_val or 0),
        coefficient_of_variation=round(cv, 2),
        is_homogeneous=cv <= 33.0,
    )
```

### 5.3. VAT Normalization
Prices in `contracts.json` have heterogeneous VAT rates (`"20%"`, `"10%"`, `"Без НДС"`). They **must** be normalized to a common base before comparison.

```python
def normalize_vat(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize all prices to 'without VAT' base for fair comparison."""
    vat_map = {
        "20%": 1.20,
        "10%": 1.10,
        "Без НДС": 1.0,
    }

    return df.with_columns(
        pl.when(pl.col("Ставка НДС") == "20%")
          .then(pl.col("Цена за единицу") / 1.20)
          .when(pl.col("Ставка НДС") == "10%")
          .then(pl.col("Цена за единицу") / 1.10)
          .otherwise(pl.col("Цена за единицу"))
          .alias("Цена за единицу (без НДС)")
    )
```

### 5.4. Time-Weighted Pricing
More recent contract prices should carry more weight in the final calculation.

```python
def apply_time_weights(df: pl.DataFrame) -> pl.DataFrame:
    """Add a weight column: newer contracts → higher weight."""
    from datetime import datetime

    now = datetime.now()
    return df.with_columns(
        (1.0 / (1.0 + ((pl.lit(now) - pl.col("Дата заключения контракта"))
                        .dt.total_days() / 365.0)))
        .alias("time_weight")
    )
```

## 6. NMCK Calculation Formulas (44-ФЗ / Hackathon Rules)

### 6.1. Core Formulas
The NMCK is calculated using the **comparable prices method** (метод сопоставимых рыночных цен):

**Step 1: Weighted Average Unit Price**
$$
\bar{Ц} = \frac{\sum_{i=1}^{n} Ц_i \cdot w_i}{\sum_{i=1}^{n} w_i}
$$
Where `Цi` = unit price (VAT-normalized), `wi` = time weight.

**Step 2: Coefficient of Variation**
$$
V = \frac{\sigma}{\bar{Ц}} \times 100\%
$$
If `V ≤ 33%` → prices are homogeneous, calculation is valid.
If `V > 33%` → sample is heterogeneous, **user must be warned** and asked to refine selection.

**Step 3: NMCK per Unit**
$$
НМЦК_{ед} = \bar{Ц} \times K_{инфл}
$$
Where `K_инфл` = inflation coefficient (optional, default = 1.0).

**Step 4: Total NMCK**
$$
НМЦК = НМЦК_{ед} \times Q
$$
Where `Q` = required quantity.

**Step 5: Acceptable Price Range**
$$
Ц_{min} = \bar{Ц} \times (1 - V/100)
$$
$$
Ц_{max} = \bar{Ц} \times (1 + V/100)
$$

### 6.2. NMCK Calculation Node
```python
# src/graph/nodes.py
def calculate_nmcc(state: PipelineState) -> PipelineState:
    """Calculate NMCK using weighted average and validate homogeneity."""
    prices = state.user_approved_prices
    if not prices:
        state.error = "Нет одобренных цен для расчёта"
        return state

    df = pl.DataFrame(prices)
    df = apply_time_weights(df)

    price_col = "Цена за единицу (без НДС)"

    # Weighted average
    weighted_sum = df.select(
        (pl.col(price_col) * pl.col("time_weight")).sum()
    ).item()
    weight_sum = df.select(pl.col("time_weight").sum()).item()
    weighted_avg = weighted_sum / weight_sum if weight_sum else 0

    # Standard deviation & CV
    std_dev = df.select(pl.col(price_col).std()).item() or 0
    cv = (std_dev / weighted_avg * 100) if weighted_avg > 0 else 0

    state.weighted_average_price = round(weighted_avg, 2)
    state.coefficient_of_variation = round(cv, 2)
    state.is_homogeneous = cv <= 33.0
    state.nmck_per_unit = round(weighted_avg * state.inflation_coefficient, 2)
    state.total_nmck = round(state.nmck_per_unit * state.quantity, 2)
    state.price_range_min = round(weighted_avg * (1 - cv / 100), 2)
    state.price_range_max = round(weighted_avg * (1 + cv / 100), 2)
    state.current_step = "nmcc_calculated"
    return state
```

## 7. LangGraph State Machine (Human-in-the-Loop)

### 7.1. Graph State Definition
```python
from pydantic import BaseModel, Field
from typing import Any

class PipelineState(BaseModel):
    session_id: str
    target_cte_name: str
    target_category: str | None = None          # For hybrid search filtering
    region_filter: str | None = None
    quantity: float = 1.0                        # Required quantity for total NMCK
    inflation_coefficient: float = 1.0           # Inflation adjustment

    # State 1: Analog Search
    retrieved_analogs: list[dict[str, Any]] = Field(default_factory=list)
    user_approved_analogs: list[dict[str, Any]] = Field(default_factory=list)

    # State 2: Price Fetching & Filtering
    raw_prices: list[dict[str, Any]] = Field(default_factory=list)
    filtered_prices: list[dict[str, Any]] = Field(default_factory=list)
    outlier_prices: list[dict[str, Any]] = Field(default_factory=list)
    user_approved_prices: list[dict[str, Any]] = Field(default_factory=list)

    # State 3: Calculation
    weighted_average_price: float = 0.0
    coefficient_of_variation: float = 0.0
    is_homogeneous: bool = True                  # CV ≤ 33%
    nmck_per_unit: float = 0.0
    total_nmck: float = 0.0
    price_range_min: float = 0.0
    price_range_max: float = 0.0

    # State 4: Document
    document_url: str | None = None

    # Explainability
    justification: list[dict[str, Any]] = Field(default_factory=list)
    # Each entry: {cte_id, name, price, region, date, match_reason, cosine_score}

    error: str | None = None
    current_step: str = "init"
```

### 7.2. Graph Nodes & Edges
```
┌─────────────────┐
│ search_analogs   │ ← Hybrid: vector + category filter + attribute ranking
└────────┬────────┘
         │ INTERRUPT
         ▼
┌──────────────────────────┐
│ wait_for_analog_approval │ ← User reviews/edits/adds analogs
└────────┬─────────────────┘
         ▼
┌────────────────┐
│ process_prices │ ← Polars filter by CTE IDs + region + date
│                │   + VAT normalization + IsolationForest
│                │   + CV check
└────────┬───────┘
         │ INTERRUPT
         ▼
┌─────────────────────────┐
│ wait_for_price_approval │ ← User reviews prices, can add manual prices
└────────┬────────────────┘
         ▼
┌────────────────┐
│ calculate_nmcc │ ← Weighted avg + CV validation + NMCK formula
└────────┬───────┘
         ▼
┌─────────────────────┐
│ generate_document   │ ← .docx with full justification
└─────────────────────┘
```

**Node Details:**

1.  **`search_analogs`**: Embeds `target_cte_name + target_category`. Queries Qdrant with **category filter**. Post-ranks by attribute overlap. Builds `justification` entries with `match_reason`. Transitions to `wait_for_analog_approval`.

2.  **`wait_for_analog_approval`**: Human node. User can:
    - Accept/reject individual analogs
    - Manually add CTE IDs
    - Edit the category filter and re-search

3.  **`process_prices`**: Uses **Polars** to filter `contracts.json` by approved CTE IDs (`Идентификатор СТЕ по контракту`), date window (configurable, default 12 months), and region. Normalizes VAT. Applies `IsolationForest`. Computes coefficient of variation. Transitions to `wait_for_price_approval`.

4.  **`wait_for_price_approval`**: Human node. User can:
    - Remove/add individual prices
    - Input manual prices for items with no data
    - See outlier explanation
    - See CV warning if `V > 33%`

5.  **`calculate_nmcc`**: Applies time-weighted average, official NMCK formula, calculates range. See §6.

6.  **`generate_document`**: Populates `.docx` template with:
    - Selected analogs with match reasoning
    - Price table with source contracts
    - Outlier list with removal justification
    - CV value and homogeneity status
    - Final NMCK with formula breakdown
    - Acceptable price range

## 8. Explainability & Justification (35 баллов)
Every step produces traceable justification:

| Step | What is Explained |
|---|---|
| Analog Search | Cosine similarity score, category match, attribute overlap % |
| Price Filtering | Date range applied, region filter, # of contracts found |
| Outlier Removal | Which prices were removed and why (IsolationForest score) |
| NMCK Calculation | Formula with plugged-in values, CV value, homogeneity verdict |

Each justification entry in the state:
```python
{
    "cte_id": 34863000,
    "name": "Мусорные пакеты 35л",
    "price_without_vat": 198.33,
    "original_price": 238.0,
    "vat_rate": "20%",
    "region": "Москва",
    "contract_date": "2025-10-15",
    "match_reason": "Категория: Пакеты полимерные (exact match). Cosine: 0.91. Атрибуты: Объем=35 (match), Цвет=черный (match). Совпадение 2/5 атрибутов.",
    "cosine_score": 0.91,
    "attribute_overlap": 0.4,
    "time_weight": 0.83,
}
```

## 9. Embedding via ONNX Runtime (Performance)
The model `pplx-embed-v1-0.6b` supports ONNX natively. Using ONNX Runtime instead of `sentence-transformers` provides **3-5× faster inference** on CPU.

```python
# src/ml/embedder.py
import onnxruntime as ort
from transformers import AutoTokenizer
import numpy as np

class OnnxEmbedder:
    def __init__(self, model_path: str = "perplexity-ai/pplx-embed-v1-0.6b"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.session = ort.InferenceSession(f"{model_path}/onnx/model.onnx")

    def encode(self, texts: list[str]) -> np.ndarray:
        """Returns int8 quantized embeddings (1024-dim)."""
        tokenized = self.tokenizer(
            texts, padding=True, truncation=True, return_tensors="np"
        )
        onnx_inputs = {
            "input_ids": tokenized["input_ids"].astype(np.int64),
            "attention_mask": tokenized["attention_mask"].astype(np.int64),
        }
        outputs = self.session.run(
            [out.name for out in self.session.get_outputs()],
            onnx_inputs,
        )
        # outputs[2] = int8 embeddings (1024-dim)
        return outputs[2]
```

## 10. Containerization & Deployment (Docker Compose & uv)

### 10.1. Dockerfile
```dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/usr/local

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Pre-download model + ONNX weights (offline requirement)
ENV HF_HOME=/app/.cache/huggingface
RUN uv run python -c "\
from transformers import AutoTokenizer; \
AutoTokenizer.from_pretrained('perplexity-ai/pplx-embed-v1-0.6b', trust_remote_code=True); \
from huggingface_hub import hf_hub_download; \
hf_hub_download('perplexity-ai/pplx-embed-v1-0.6b', 'onnx/model.onnx')"

# Enforce offline mode for runtime
ENV HF_DATASETS_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Copy project files
COPY . .

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 10.2. docker-compose.yml
```yaml
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

## 11. API Endpoints (FastAPI)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/session/start` | Start new NMCK calculation session |
| `POST` | `/api/session/{id}/search` | Trigger analog search (body: `{cte_name, category?, region?}`) |
| `GET` | `/api/session/{id}/analogs` | Get found analogs for review |
| `POST` | `/api/session/{id}/analogs/approve` | User approves/edits analog list |
| `GET` | `/api/session/{id}/prices` | Get filtered prices for approved analogs |
| `POST` | `/api/session/{id}/prices/approve` | User approves/edits price list, can add manual prices |
| `GET` | `/api/session/{id}/calculation` | Get NMCK calculation result with justification |
| `POST` | `/api/session/{id}/recalculate` | Recalculate with updated parameters |
| `GET` | `/api/session/{id}/document` | Download generated .docx justification |

## 12. Agent Directives & Documentation (MCP context7)

**CRITICAL INSTRUCTION FOR THE AI IMPLEMENTATION AGENT:**
Before generating implementation code, you **MUST** use MCP context7 to retrieve up-to-date docs for:
1.  **Polars:** `pl.DataFrame()` constructor from list of dicts, `pl.col()` expressions, datetime parsing with `%.f` fractional seconds.
2.  **LangGraph:** `StateGraph`, `MemorySaver`, `END` transitions, interrupt nodes.
3.  **FastAPI & Pydantic V2:** `@asynccontextmanager` lifespan, `Pydantic` `Field` validations.
4.  **Qdrant Client:** `models.Filter`, `models.FieldCondition`, `models.MatchValue` for payload filtering.
5.  **ONNX Runtime:** `InferenceSession`, input/output names mapping for pplx-embed.
6.  **uv:** `uv sync`, `uv run` CLI commands for Dockerfile.

*Do not rely on pre-2024 training data for LangGraph and Polars API surfaces.*