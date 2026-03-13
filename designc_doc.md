## 1. System Architecture Overview

This system is designed as a modular, 100% offline-capable application split into two separate microservices orchestrated via Docker Compose. This architecture ensures that standard web requests are completely isolated from CPU-bound Machine Learning inference tasks, strictly adhering to the hackathon's constraints.

* **Repository 1 (`tender-backend`)**: The core API, database orchestrator, and calculation engine. Responsible for HTTP handling, PostgreSQL/pgvector interactions, Polars data aggregations (time decay, region scoring), and `.docx` report generation.
* **Repository 2 (`tender-ml-worker`)**: An isolated, internal microservice dedicated to Heavy ML tasks. Runs ONNX embeddings, GGUF local Small Language Models (SLM) for data normalization, and Scikit-Learn algorithms for anomaly detection.

---

## 2. REPOSITORY 1: BACKEND SERVICE (`tender-backend`)

### 2.1. Tech Stack (Strict Requirements)

* **Runtime:** Python 3.12
* **Web Framework:** FastAPI + Pydantic v2
* **State Machine & Agentic Workflow:** `langgraph` + `langchain_core` (To orchestrate the complex steps of NMCC calculation and Human-in-the-loop workflows).
* **Database:** PostgreSQL 16+ with `pgvector` extension.
* **ORM:** SQLAlchemy 2.0 (using `asyncpg` for asynchronous database operations).
* **Data Processing:** `polars` (Strictly use Polars instead of Pandas for performance optimization during NMCC aggregation).
* **Document Generation:** `python-docx` combined with `Jinja2` templates.
* **HTTP Client:** `httpx` (for async communication with the ML Worker).
* **Dependency Management:** `uv`

### 2.2. Database Schema Definition

The database models must strictly map to the provided JSON dataset structures while maintaining relational integrity.

**Table: `ste_catalog` (Maps to the `cte.json` dataset)**

* `id`: `UUID` (Primary Key, default: `uuid4`)
* `ste_id`: `String` (Indexed. Maps to *«Идентификатор СТЕ»*, e.g., "34863000")
* `name`: `String` (Maps to *«Наименование СТЕ»*)
* `category`: `String` (Maps to *«Категория»*)
* `manufacturer`: `String` (Maps to *«Производитель»*)
* `raw_characteristics`: `Text` (Raw array format from JSON)
* `parsed_characteristics`: `JSONB` (Populated asynchronously via ML Worker's SLM parsing, transforming arrays into standard Key-Value pairs)
* `embedding`: `Vector(384)` (Generated via ML Worker's `ru-e5-small` model. Requires `HNSW` index with `vector_cosine_ops` for fast similarity search).

**Table: `contracts` (Maps to the `contracts.json` dataset)**

* `id`: `UUID` (Primary Key, default: `uuid4`)
* `contract_id`: `String` (Indexed. Maps to *«Идентификатор контракта»*)
* `ste_id`: `String` (Foreign Key referencing `ste_catalog.ste_id`, Indexed. Maps to *«Идентификатор СТЕ по контракту»*)
* `purchase_name`: `String` (Maps to *«Наименование закупки»*)
* `quantity`: `Numeric` (Maps to *«Количество»*)
* `price_per_unit`: `Numeric` (Maps to *«Цена за единицу»*. **Crucial field for NMCC math**).
* `contract_date`: `DateTime` (Maps to *«Дата заключения контракта»*. Indexed for fast time-decay filtering).
* `customer_region`: `String` (Maps to *«Регион заказчика»*)
* `supplier_region`: `String` (Maps to *«Регион поставщика»*)
* `vat_rate`: `String` (Maps to *«Ставка НДС»*)

### 2.3. Public API Specification (Exposed to UI)

#### `GET /api/v1/ste/search`

* **Description:** Hybrid semantic search for STE analogs with historical price fetching.
* **Request Query Parameters:**
* `query` (string, required): e.g., "Пакеты для мусора 35л"
* `target_region` (string, optional): Used to calculate logistics confidence scores.
* `months_depth` (int, default=12): Ignore contracts older than X months from the current date.


* **Execution Flow:**
1. Send composite `query` to `ML Worker` (`/internal/ml/embed`) to get `[float]` vector.
2. Execute async SQLAlchemy query using pgvector's `<=>` operator against `ste_catalog.embedding`, adding a boost for exact category matches.
3. Apply `JOIN` on `contracts` table.
4. Apply `WHERE contract_date >= current_date - months_depth`.


* **Response (`200 OK`):**
```json
{
  "results": [
    {
      "ste_id": "34863000",
      "name": "Мусорные пакеты 35л",
      "similarity_score": 0.92,
      "parsed_characteristics": {"Объем": 35.0, "Цвет": "черный"},
      "historical_prices": [
        {"contract_id": "uuid", "date": "2025-10-01", "price": 120.50, "region": "Москва"},
        {"contract_id": "uuid", "date": "2025-11-15", "price": 125.00, "region": "ЦФО"}
      ]
    }
  ]
}

```



#### `POST /api/v1/nmck/calculate`

* **Description:** Processes user-selected contracts, detects outliers via ML, applies Polars calculations, and returns the final NMCC.
* **Request Body:**
```json
{
  "target_ste_id": "34863000",
  "target_region": "Москва",
  "selected_prices": [120.50, 125.00, 118.00, 5000.00, 122.00]
}

```


* **Execution Flow (Orchestrated by LangGraph State Machine):**
1. **Node `ParseInput`**: Receive `target_ste_id` and initial parameters.
2. **Node `FetchContracts`**: Use Polars to load relevant contracts from Database.
3. **Node `DetectOutliers`**: Send `prices` to `ML Worker` (`/internal/ml/detect-outliers`). Receive `valid_prices` and `outliers`.
4. **Node `HumanInTheLoop` (Interrupt State)**: Return state to UI. User visually reviews outliers, manually adds/edits prices, and confirms.
5. **Node `CalculateMath`**: Load confirmed `valid_prices` into a `polars.Series`. Calculate Variation Coefficient ($v$) and Average Price using strict Polars math.
6. **Node `ExplainableAI`**: Draft a human-readable string explaining the data changes (e.g., "Outlier at 5000.00 was removed, leaving 4 reliable prices...").

* **Response (`200 OK` - from HumanInTheLoop or Final State):**
```json
{
  "nmck_value": 121.37,
  "variation_coefficient": 0.024,
  "valid_prices_used": [120.50, 125.00, 118.00, 122.00],
  "detected_outliers": [5000.00],
  "requires_manual_input": true,
  "ai_explanation": "Из выборки исключена аномальная цена 5000.00, превышающая медиану."
}

```



#### `POST /api/v1/nmck/report`

* **Description:** Generates the final `.docx` document.
* **Execution Flow:** Injects the NMCC calculation payload into a pre-defined `.docx` template using `python-docx`. Returns a `FileResponse` (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`).

---

## 3. REPOSITORY 2: ML WORKER (`tender-ml-worker`)

### 3.1. Tech Stack & Locked Models

* **Runtime:** Python 3.12
* **Web Framework:** FastAPI (Internal routing only, no public access).
* **Semantic Search Model:** `ai-forever/ru-e5-small`
* *Implementation strict rule:* Must be exported to `.onnx` format (INT8 quantization) and executed via `onnxruntime` on CPU. Do NOT use PyTorch `transformers` pipeline to save RAM/CPU. Dimension: `384`.


* **Data Normalization Model (SLM):** `Qwen3-8B-Instruct-GGUF` (Q4_K_M).
* *Implementation strict rule:* Executed via `llama-cpp-python`. Must utilize Llama.cpp's `grammar` parameter to force strictly structured JSON Schema output and prevent hallucinations. (Chosen due to superior 2026 CPU performance and zero-shot table parsing capabilities).


* **Anomaly Detection Model:** `sklearn.ensemble.IsolationForest`
* *Implementation strict rule:* `contamination="auto"`.



### 3.2. Internal API Specification (Called ONLY by Backend)

#### `POST /internal/ml/embed`

* **Request:** `{"text": "[КАТЕГОРИЯ] Пакеты [НАЗВАНИЕ] Мусорные пакеты 35л [ХАРАКТЕРИСТИКИ] Цвет: черный"}`
* **Execution Flow:** Tokenize text -> Run through ONNX runtime `ru-e5-small` -> perform mean pooling -> return L2-normalized vector.
* **Response:** `{"embedding": [0.012, -0.055, 0.891, ...]} // length 384`

#### `POST /internal/ml/parse-characteristics`

* **Request:** `{"raw_text": "[[\"Количество в упаковке\", \"30.00000\"], [\"Толщина, мкм\", \"50.00000\"]]"}`
* **Execution Flow:** 1.  Construct Prompt: *"Convert this array to a flat JSON object standardizing unit names."*
2.  Invoke `llama-cpp-python` engine with GGUF model and JSON Schema enforcement.
* **Response:**
```json
{
  "parsed_json": {
    "Количество в упаковке": 30.0,
    "Толщина": 50.0
  }
}

```



#### `POST /internal/ml/detect-outliers`

* **Request:** `{"prices": [23760.0, 24000.0, 23500.0, 1500.0, 95000.0]}`
* **Execution Flow:** Convert list to `numpy` array shape `(-1, 1)`. Run `IsolationForest().fit_predict()`. Values marked as `-1` are outliers.
* **Response:** ```json
{
"valid_prices": [23760.0, 24000.0, 23500.0],
"outliers": [1500.0, 95000.0]
}
```


```



---

## 4. DEPLOYMENT CONFIGURATION (`docker-compose.yml`)

The following Compose file orchestrates the entire system locally. The AI Agent must place this at the root of the project (above the two repositories).

```yaml
version: '3.8'

services:
  database:
    image: ankane/pgvector:latest
    container_name: tender_pgvector
    environment:
      POSTGRES_USER: tender_user
      POSTGRES_PASSWORD: tender_password
      POSTGRES_DB: tenderhack_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tender_user -d tenderhack_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  ml_worker:
    build: 
      context: ./tender-ml-worker
      dockerfile: Dockerfile
    container_name: tender_ml_worker
    expose:
      - "8001"
    volumes:
      - ./model_weights:/app/models # Maps local weights to avoid downloading inside container
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]

  backend:
    build: 
      context: ./tender-backend
      dockerfile: Dockerfile
    container_name: tender_backend
    depends_on:
      database:
        condition: service_healthy
      ml_worker:
        condition: service_started
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://tender_user:tender_password@database:5432/tenderhack_db
      - ML_SERVICE_URL=http://ml_worker:8001
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

volumes:
  pgdata:

```

---
