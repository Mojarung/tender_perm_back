


# SYSTEM DESIGN DOCUMENT: Intelligent NMCK Calculation Service (Tender Hack - Perm 2026)

## 1. System Architecture Overview
This system is designed as a modular, offline-capable application split into two separate microservices. This architecture ensures that I/O-bound backend operations are completely isolated from CPU-bound Machine Learning inference tasks, strictly adhering to the 2026 hackathon constraints (no external APIs, fully local execution on standard servers).

*   **Repository 1 (`tender-backend`)**: The core API, database orchestrator, and calculation engine. Responsible for HTTP handling, PostgreSQL/pgvector interactions, Polars data aggregations, and `.docx` report generation.
*   **Repository 2 (`tender-ml-worker`)**: An isolated, internal microservice dedicated to Heavy ML tasks. Runs ONNX embeddings, GGUF local Small Language Models (SLM) for data normalization, and Scikit-Learn algorithms for anomaly detection.

---

## 2. REPOSITORY 1: BACKEND SERVICE (`tender-backend`)

### 2.1. Tech Stack (Strict Requirements)
*   **Runtime:** Python 3.12
*   **Web Framework:** FastAPI + Pydantic v2
*   **Database:** PostgreSQL 16+ with `pgvector` extension.
*   **ORM:** SQLAlchemy 2.0 (using `asyncpg` for asynchronous database operations).
*   **Data Processing:** `polars` (Must use Polars instead of Pandas for performance optimization during NMCK aggregation).
*   **Document Generation:** `python-docx` combined with `Jinja2` templates.
*   **HTTP Client:** `httpx` (for async communication with the ML Worker).
*   **Dependency Management:** `uv`

### 2.2. Database Schema Definition
The database models must strictly map to the provided dataset screenshots. 

**Table: `ste_catalog` (Maps to the STE Catalog dataset)**
*   `id`: `UUID` (Primary Key, default: `uuid4`)
*   `ste_id`: `String` (Indexed. Maps to *«Идентификатор»*, e.g., "34863000")
*   `name`: `String` (Maps to *«Наименование СТЕ»*, e.g., "Мусорные пакеты 35л")
*   `category`: `String` (Maps to *«Категория»*, e.g., "Пакеты полимерные...")
*   `manufacturer`: `String` (Maps to *«Производитель»*)
*   `raw_characteristics`: `Text` (Maps to *«характеристики СТЕ»*. Raw string: "Количество в упаковке:30.00000;Толщина:50...")
*   `parsed_characteristics`: `JSONB` (Populated asynchronously via ML Worker's SLM parsing)
*   `embedding`: `Vector(768)` (Generated via ML Worker. Requires `HNSW` index with `vector_cosine_ops` for fast similarity search).

**Table: `contracts` (Maps to the Historical Contracts dataset)**
*   `id`: `UUID` (Primary Key, default: `uuid4`)
*   `ste_id`: `String` (Foreign Key referencing `ste_catalog.ste_id`, Indexed. Maps to *«Идентификатор позиции»*)
*   `purchase_name`: `String` (Maps to *«Наименование закупки»*)
*   `quantity`: `Numeric` (Maps to *«Количество»*)
*   `unit`: `String` (Maps to *«Единица измерения»*, e.g., "шт")
*   `initial_cost`: `Numeric` (Maps to *«Начальная Стоимость»*)
*   `discount_percent`: `Numeric` (Maps to *«% снижения»*)
*   `vat_rate`: `String` (Maps to *«Ставка НДС»*, e.g., "20%")
*   `contract_date`: `DateTime` (Maps to *«Дата заключения контракта»*. Indexed for fast time-decay filtering)
*   `customer_inn`: `String` (Maps to *«ИНН заказчика»*)
*   `customer_region`: `String` (Maps to *«Регион заказчика»*, e.g., "Москва")
*   `supplier_inn`: `String` (Maps to *«ИНН поставщика»*)
*   `supplier_region`: `String` (Maps to *«Регион поставщика»*)
*   `price_per_unit`: `Numeric` (Maps to *«Цена за единицу»*. **Crucial field for NMCK math**).

### 2.3. Public API Specification (Exposed to UI)

#### `GET /api/v1/ste/search`
*   **Description:** Semantic search for STE analogs with historical price fetching.
*   **Request Query Parameters:**
    *   `query` (string, required): e.g., "Пакеты для мусора 35л"
    *   `region` (string, optional): Filter contracts by `customer_region`.
    *   `months_depth` (int, default=12): Ignore contracts older than X months from current date.
*   **Execution Flow:**
    1.  Send `query` to `ML Worker` (`/internal/ml/embed`) to get `[float]` vector.
    2.  Execute async SQLAlchemy query using pgvector's `<=>` operator against `ste_catalog.embedding`.
    3.  Apply `JOIN` on `contracts` table.
    4.  Apply `WHERE contract_date >= current_date - months_depth`.
*   **Response (`200 OK`):**
    ```json
    {
      "results":[
        {
          "ste_id": "34863000",
          "name": "Мусорные пакеты 35л",
          "similarity_score": 0.92,
          "parsed_characteristics": {"Объем": 35.0, "Цвет": "черный"},
          "historical_prices":[
            {"contract_id": "uuid", "date": "2025-10-01", "price": 120.50},
            {"contract_id": "uuid", "date": "2025-11-15", "price": 125.00}
          ]
        }
      ]
    }
    ```

#### `POST /api/v1/nmck/calculate`
*   **Description:** Processes user-selected contracts, detects outliers via ML, and calculates final NMCK.
*   **Request Body:**
    ```json
    {
      "target_ste_id": "34863000",
      "selected_prices":[120.50, 125.00, 118.00, 5000.00, 122.00]
    }
    ```
*   **Execution Flow:**
    1.  Send `selected_prices` to `ML Worker` (`/internal/ml/detect-outliers`).
    2.  Receive `valid_prices` (e.g., `[120.50, 125.00, 118.00, 122.00]`) and `outliers` (e.g., `[5000.00]`).
    3.  Load `valid_prices` into a `polars.Series`.
    4.  Calculate Variation Coefficient (v) and Average Price using Polars strict math.
*   **Response (`200 OK`):**
    ```json
    {
      "nmck_value": 121.37,
      "variation_coefficient": 0.024,
      "valid_prices_used":[120.50, 125.00, 118.00, 122.00],
      "detected_outliers": [5000.00]
    }
    ```

#### `POST /api/v1/nmck/report`
*   **Description:** Generates the final Word document.
*   **Execution Flow:** Injects the NMCK calculation payload into a pre-defined `.docx` template using `python-docx`. Returns a `FileResponse` (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`).

---

## 3. REPOSITORY 2: ML WORKER (`tender-ml-worker`)

### 3.1. Tech Stack & Locked Models
*   **Runtime:** Python 3.12
*   **Web Framework:** FastAPI (Internal routing only, no public access).
*   **Semantic Search Model:** `sberbank-ai/ru-sentence-ruBERT`
    *   *Implementation strict rule:* Must be exported to `.onnx` format and executed via `onnxruntime` on CPU. Do NOT use PyTorch `transformers` pipeline in production to save RAM/CPU. Dimension: `768`.
*   **Data Normalization Model (SLM):** `GigaChat-Nano-GGUF` (Q4_K_M quantization).
    *   *Implementation strict rule:* Executed via `llama-cpp-python`. Must utilize Llama.cpp's `grammar` parameter to force strictly structured JSON output and prevent hallucinations.
*   **Anomaly Detection Model:** `sklearn.ensemble.IsolationForest`
    *   *Implementation strict rule:* `contamination="auto"`.

### 3.2. Internal API Specification (Called ONLY by Backend)

#### `POST /internal/ml/embed`
*   **Request:** `{"text": "Радиостанция носимая цифро-аналоговая"}`
*   **Execution Flow:** Tokenize text -> Run through ONNX runtime `ru-sentence-ruBERT` -> perform mean pooling -> return L2-normalized vector.
*   **Response:** `{"embedding":[0.012, -0.055, 0.891, ...]} // length 768`

#### `POST /internal/ml/parse-characteristics`
*   **Request:** `{"raw_text": "Количество в упаковке:30.00000;Толщина, мкм:50.00000"}`
*   **Execution Flow:** 
    1.  Construct Prompt: *"Извлеки пары ключ-значение из текста. Выведи только JSON."*
    2.  Invoke `llama-cpp-python` engine with GGUF model and JSON Schema enforcement.
*   **Response:**
    ```json
    {
      "parsed_json": {
        "Количество в упаковке": 30.0,
        "Толщина, мкм": 50.0
      }
    }
    ```

#### `POST /internal/ml/detect-outliers`
*   **Request:** `{"prices":[23760.0, 24000.0, 23500.0, 1500.0, 95000.0]}`
*   **Execution Flow:** Convert list to `numpy` array shape `(-1, 1)`. Run `IsolationForest().fit_predict()`. Values marked as `-1` are outliers.
*   **Response:** 
    ```json
    {
      "valid_prices":[23760.0, 24000.0, 23500.0],
      "outliers":[1500.0, 95000.0]
    }
    ```

---

## 4. DEPLOYMENT CONFIGURATION (`docker-compose.yml`)

The following Compose file orchestrates the entire system locally. The AI Agent should place this at the root of the project (above the two repositories).

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
      test:["CMD-SHELL", "pg_isready -U tender_user -d tenderhack_db"]
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
      - ./model_weights:/app/models # Must map local weights to avoid downloading
    command:["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]

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
    command:["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

volumes:
  pgdata:
```