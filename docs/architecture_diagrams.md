# Архитектура системы расчёта НМЦК — Mermaid-диаграммы

> Модель эмбеддингов: **Perplexity Embed v1 (pplx-embed-v1-0.6b)** — локальная модель, 1024-мерные векторы
> Все компоненты работают **локально**, без внешних API

---

## 1. Общая архитектура системы (C4 — контейнерная диаграмма)

```mermaid
graph TB
    subgraph "Пользователь"
        USER["👤 Специалист по закупкам"]
    end

    subgraph "Frontend · React 19 + TypeScript"
        direction TB
        SPA["🖥️ SPA-приложение<br/>React 19 · Vite · Tailwind CSS"]
        subgraph "Страницы"
            PAGE_CREATE["📝 CreatePurchasePage<br/>Создание закупки"]
            PAGE_PIPELINE["⚙️ PipelineView<br/>Пайплайн расчёта<br/>(ReactFlow визуализация)"]
            PAGE_HISTORY["📋 HistoryPage<br/>Журнал расчётов"]
            PAGE_DETAIL["📄 HistoryDetailPage<br/>Детали закупки"]
        end
        subgraph "Компоненты"
            HEATMAP["🗺️ RegionHeatmap<br/>Карта цен по регионам РФ"]
            OPTIMIZER["📊 PriceOptimizer<br/>Оптимизация выборки<br/>(CV-анализ)"]
            TUTORIAL["❓ TutorialOverlay<br/>Обучающий тур"]
        end
    end

    subgraph "Backend · FastAPI + LangGraph"
        direction TB
        API["🚀 FastAPI Server<br/>REST API"]
        GRAPH["🔄 LangGraph Pipeline<br/>5 нод · 2 прерывания<br/>Human-in-the-Loop"]
        subgraph "Сервисы"
            SEARCH_SVC["🔍 SearchService<br/>Гибридный поиск<br/>(семантика + ключевые слова)"]
            NMCK_SVC["🧮 NMCKService<br/>Расчёт НМЦК<br/>(Приказ №567)"]
            DOC_SVC["📄 DocumentService<br/>Генерация .docx"]
            STATS_SVC["📈 StatsService<br/>IsolationForest<br/>Детектор выбросов"]
        end
        subgraph "Доступ к данным"
            CONTRACT_REPO["📦 ContractRepository<br/>~560K+ контрактов"]
            CTE_REPO["📚 CTERepository<br/>Каталог СТЕ<br/>~350K+ позиций"]
            HISTORY_REPO["💾 HistoryRepository<br/>Журнал расчётов"]
        end
    end

    subgraph "ML-слой (локальный)"
        EMBEDDER["🧠 Perplexity Embedder<br/>pplx-embed-v1-0.6b<br/>Локальная модель<br/>Размерность: 1024"]
    end

    subgraph "Хранилища данных"
        QDRANT[("🔷 Qdrant<br/>Векторная БД<br/>Коллекция: cte_catalog<br/>Косинусное расстояние")]
        DB_HISTORY[("💾 БД истории<br/>Закупки · Расчёты")]
        DB_CHECKPOINTS[("💾 БД состояний<br/>Чекпоинты пайплайна")]
        DS_CONTRACTS[("📦 База контрактов<br/>Государственные контракты")]
        DS_CTE[("📦 Каталог СТЕ<br/>Реестр товаров/услуг")]
    end

    USER -->|"HTTP/Browser"| SPA
    SPA -->|"REST API"| API
    API --> GRAPH
    GRAPH --> SEARCH_SVC
    GRAPH --> NMCK_SVC
    GRAPH --> DOC_SVC
    GRAPH --> STATS_SVC
    SEARCH_SVC --> EMBEDDER
    SEARCH_SVC --> CTE_REPO
    CTE_REPO --> QDRANT
    CONTRACT_REPO --> DS_CONTRACTS
    CTE_REPO --> DS_CTE
    HISTORY_REPO --> DB_HISTORY
    GRAPH -->|"Checkpointer"| DB_CHECKPOINTS
    NMCK_SVC --> CONTRACT_REPO
    STATS_SVC --> CONTRACT_REPO

    style USER fill:#E3F2FD,stroke:#1565C0,stroke-width:2px
    style SPA fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px
    style API fill:#FFF3E0,stroke:#E65100,stroke-width:2px
    style GRAPH fill:#F3E5F5,stroke:#6A1B9A,stroke-width:2px
    style EMBEDDER fill:#FCE4EC,stroke:#C62828,stroke-width:2px
    style QDRANT fill:#E0F7FA,stroke:#00695C,stroke-width:2px
```

---

## 2. BPMN — Основной бизнес-процесс расчёта НМЦК

```mermaid
flowchart TD
    START(("⬤ Старт"))

    subgraph "Фаза 1: Инициализация закупки"
        A1["Пользователь открывает<br/>страницу создания закупки"]
        A2["Выбор региона<br/>(89 субъектов РФ)"]
        A3["Ввод наименований<br/>товаров/услуг<br/>(1..N строк)"]
        A4["Поиск позиций<br/>в каталоге СТЕ"]
        A5{"Найдены<br/>позиции?"}
        A6["Отметка выбранных<br/>СТЕ-позиций"]
        A7["Нажатие<br/>'Рассчитать НМЦК'"]
        A8["Создание записи<br/>закупки в БД"]
    end

    subgraph "Фаза 2: Семантический поиск аналогов"
        B1["Формирование запроса:<br/>название + категория"]
        B2["Perplexity Embed v1<br/>Векторизация запроса<br/>(1024-мерный вектор)"]
        B3["Поиск в Qdrant<br/>Косинусное сходство<br/>top_k=20, threshold≥0.5"]
        B4{"Результатов ≥ 3<br/>с фильтром<br/>категории?"}
        B5["Повторный поиск<br/>БЕЗ фильтра категории"]
        B6["Гибридное ранжирование:<br/>• Семантика (50%)<br/>• Ключевые слова (40%)<br/>• Атрибуты (10%)<br/>• Бонус категории (+5%)"]
        B7["Возврат top-10<br/>ранжированных аналогов"]
    end

    subgraph "Фаза 3: ⏸️ Утверждение аналогов (HITL #1)"
        C1["Отображение списка<br/>найденных аналогов"]
        C2["Показ метаданных:<br/>• Кол-во контрактов<br/>• Регионы поставок<br/>• Уникальные поставщики<br/>• Ед. измерения"]
        C3{"Пользователь<br/>выбирает аналоги"}
        C4["Добавление<br/>CTE ID вручную<br/>(опционально)"]
        C5["Добавление<br/>ручных цен<br/>(опционально)"]
        C6["Выбор единиц<br/>измерения"]
        C7["Нажатие<br/>'Утвердить аналоги'"]
    end

    subgraph "Фаза 4: Сбор и фильтрация цен"
        D1["Запрос контрактов<br/>по CTE ID аналогов"]
        D2["Фильтрация:<br/>• Регион (если задан)<br/>• Период (12 мес)<br/>• Единицы измерения"]
        D3{"Найдены<br/>контракты?"}
        D4["Расширение: поиск<br/>по ВСЕМ регионам"]
        D5{"Найдены?"}
        D6["Расширение периода<br/>до 24 месяцев"]
        D7["Расчёт временных весов:<br/>w = 1/(1 + days/365)"]
        D8["IsolationForest:<br/>детекция выбросов<br/>(contamination=auto)"]
        D9["Разделение на:<br/>✅ Валидные цены<br/>❌ Выбросы (с причиной)"]
    end

    subgraph "Фаза 5: ⏸️ Утверждение цен (HITL #2)"
        E1["Отображение таблицы цен<br/>с флагами выбросов"]
        E2["PriceOptimizer:<br/>расчёт CV, рекомендации<br/>по удалению"]
        E3["RegionHeatmap:<br/>тепловая карта<br/>цен по регионам"]
        E4{"Пользователь<br/>утверждает выборку"}
        E5["Добавление<br/>ручных цен<br/>(опционально)"]
        E6["Нажатие<br/>'Утвердить цены'"]
    end

    subgraph "Фаза 6: Расчёт НМЦК"
        F1["Повторный анализ<br/>утверждённых цен"]
        F2["Расчёт статистик:<br/>• Медиана<br/>• Среднее<br/>• Std. отклонение<br/>• CV = (σ/μ)×100%"]
        F3{"CV ≤ 33%?"}
        F4["Однородная выборка:<br/>база = средневзвешенная<br/>Ц_avg = Σ(Цi×wi)/Σ(wi)"]
        F5["Неоднородная выборка:<br/>база = медиана"]
        F6["НМЦК_ед = база × К_инфл"]
        F7["НМЦК = НМЦК_ед × кол-во"]
        F8["Диапазон цен:<br/>±(CV/100), max ±50%"]
    end

    subgraph "Фаза 7: Генерация документа"
        G1["Формирование .docx<br/>по Приказу №567"]
        G2["Разделы документа:<br/>1. Характеристики<br/>2. Метод (сопоставимых цен)<br/>3. Источники цен<br/>4. Формулы расчёта<br/>5. Таблица цен×весов<br/>6. Однородность (CV%)<br/>7. Исключённые выбросы<br/>8. Итого НМЦК (руб + прописью)<br/>9. Блок подписей"]
        G3["Сохранение документа<br/>в хранилище"]
    end

    subgraph "Фаза 8: Сохранение результатов"
        H1["Запись результатов<br/>в БД истории"]
        H2["Обновление статуса<br/>закупки"]
        H3{"Все позиции<br/>рассчитаны?"}
        H4["Отображение<br/>итоговой сводки"]
        H5["Генерация<br/>консолидированного .docx"]
    end

    FINISH(("⬤ Финиш"))

    START --> A1 --> A2 --> A3 --> A4 --> A5
    A5 -->|"Да"| A6
    A5 -->|"Нет"| A3
    A6 --> A7 --> A8

    A8 --> B1 --> B2 --> B3 --> B4
    B4 -->|"Да"| B6
    B4 -->|"Нет"| B5 --> B6
    B6 --> B7

    B7 --> C1 --> C2 --> C3
    C3 --> C4 --> C5 --> C6 --> C7

    C7 --> D1 --> D2 --> D3
    D3 -->|"Да"| D7
    D3 -->|"Нет (есть регион)"| D4 --> D5
    D5 -->|"Да"| D7
    D5 -->|"Нет"| D6 --> D7
    D7 --> D8 --> D9

    D9 --> E1 --> E2 --> E3 --> E4
    E4 --> E5 --> E6

    E6 --> F1 --> F2 --> F3
    F3 -->|"Да (однородная)"| F4
    F3 -->|"Нет (неоднородная)"| F5
    F4 --> F6
    F5 --> F6
    F6 --> F7 --> F8

    F8 --> G1 --> G2 --> G3

    G3 --> H1 --> H2 --> H3
    H3 -->|"Нет"| B1
    H3 -->|"Да"| H4 --> H5 --> FINISH

    style START fill:#4CAF50,stroke:#2E7D32,color:#fff
    style FINISH fill:#F44336,stroke:#C62828,color:#fff
    style C3 fill:#FF9800,stroke:#E65100,color:#fff
    style E4 fill:#FF9800,stroke:#E65100,color:#fff
    style F3 fill:#2196F3,stroke:#1565C0,color:#fff
    style B4 fill:#2196F3,stroke:#1565C0,color:#fff
    style D3 fill:#2196F3,stroke:#1565C0,color:#fff
    style D5 fill:#2196F3,stroke:#1565C0,color:#fff
    style H3 fill:#2196F3,stroke:#1565C0,color:#fff
    style A5 fill:#2196F3,stroke:#1565C0,color:#fff
```

---

## 3. LangGraph — Конечный автомат пайплайна

```mermaid
stateDiagram-v2
    [*] --> init: Старт сессии

    state "perform_search" as search {
        [*] --> embed_query: Формирование запроса
        embed_query --> qdrant_search: Perplexity Embed v1\n→ 1024-мерный вектор
        qdrant_search --> check_count: Qdrant cosine search\ntop_k=20
        check_count --> retry_no_filter: results < 3 && category
        check_count --> hybrid_rank: results >= 3
        retry_no_filter --> hybrid_rank: Merge results
        hybrid_rank --> [*]: Top-10 аналогов\nсохранены в state
    }

    state "wait_for_analogs ⏸️" as wait_analogs {
        [*] --> show_analogs: interrupt()
        show_analogs --> user_selects: Пользователь\nпросматривает аналоги
        user_selects --> add_manual: + ручные CTE ID
        add_manual --> add_prices: + ручные цены
        add_prices --> set_units: Выбор ед. измерения
        set_units --> [*]: Command(resume=data)
    }

    state "process_prices" as prices {
        [*] --> fetch_contracts: Запрос контрактов
        fetch_contracts --> filter_region: Фильтр: регион
        filter_region --> check_empty: Результат
        check_empty --> expand_all_regions: 0 записей → все регионы
        check_empty --> add_weights: > 0 записей
        expand_all_regions --> expand_24m: 0 → расширить до 24 мес
        expand_all_regions --> add_weights: > 0
        expand_24m --> add_weights
        add_weights --> isolation_forest: w = 1/(1+days/365)
        isolation_forest --> split_results: IsolationForest\ncontamination=auto
        split_results --> price_interrupt: valid / outliers
        price_interrupt --> user_reviews: interrupt()
        user_reviews --> [*]: Command(resume=data)
    }

    state "calculate_nmcc" as calc {
        [*] --> re_analyze: analyze_prices()
        re_analyze --> compute_stats: Медиана, среднее, CV
        compute_stats --> check_cv: CV ≤ 33%?
        check_cv --> use_weighted: Однородная → Ц_avg
        check_cv --> use_median: Неоднородная → медиана
        use_weighted --> nmck_formula
        use_median --> nmck_formula
        nmck_formula --> [*]: НМЦК = база × К_инфл × кол-во
    }

    state "generate_document" as doc {
        [*] --> build_docx: Генерация документа
        build_docx --> write_sections: 9 разделов\nпо Приказу №567
        write_sections --> save_file: Сохранение .docx
        save_file --> [*]: document_path → state
    }

    init --> search
    search --> wait_analogs: current_step = analogs_found
    wait_analogs --> prices: current_step = analogs_approved
    prices --> calc: current_step = prices_approved
    calc --> doc: current_step = nmcc_calculated
    doc --> [*]: current_step = document_generated
```

---

## 4. Sequence-диаграмма — Полный цикл взаимодействия Frontend ↔ Backend

```mermaid
sequenceDiagram
    actor User as 👤 Пользователь
    participant FE as 🖥️ Frontend<br/>(React SPA)
    participant API as 🚀 FastAPI<br/>(Backend)
    participant LG as 🔄 LangGraph<br/>(Pipeline)
    participant EMB as 🧠 Perplexity<br/>Embed v1
    participant QD as 🔷 Qdrant<br/>(Векторная БД)
    participant DATA as 📊 Data Layer<br/>(Контракты)
    participant ML as 📈 IsolationForest<br/>(Аналитика)
    participant DB as 💾 БД<br/>(История)
    participant DOC as 📄 Генератор<br/>документов

    Note over User,DOC: ═══════════ Фаза 1: Создание закупки ═══════════

    User->>FE: Открыть /create
    FE->>API: GET /api/history/recent
    API->>DB: Запрос последних закупок
    DB-->>API: Список закупок
    API-->>FE: PurchaseListResponse

    User->>FE: Выбрать регион
    User->>FE: Ввести название товара
    FE->>API: GET /cte/search?q=...
    API-->>FE: Результаты поиска СТЕ
    User->>FE: Отметить позиции ✓
    User->>FE: Нажать "Рассчитать НМЦК"

    FE->>API: POST /api/history
    API->>DB: Создание записи закупки
    DB-->>API: purchase_id
    API-->>FE: {purchase_id}

    Note over User,DOC: ═══════════ Фаза 2: Запуск пайплайна (для каждой позиции) ═══════════

    loop Для каждой выбранной СТЕ-позиции
        FE->>API: POST /api/session/start<br/>{cte_name, category, region, quantity}
        API->>LG: graph.invoke(initial_state)

        Note over LG,QD: ── Нода: perform_search ──

        LG->>EMB: encode_single(query_text)
        EMB->>EMB: Локальный инференс<br/>model: pplx-embed-v1-0.6b<br/>dimensions: 1024
        EMB-->>LG: float[1024]
        LG->>QD: search(vector, category_filter, top_k=20)
        QD-->>LG: Ранжированные результаты
        LG->>LG: rank_search_results()<br/>hybrid_score = 0.5×cosine + 0.4×keyword + 0.1×attr

        Note over LG: ── Нода: wait_for_analogs ──
        LG->>LG: interrupt() ⏸️

        LG-->>API: state + __interrupt__
        API-->>FE: {session_id, step: "waiting_for_analog_approval"}
    end

    Note over User,DOC: ═══════════ Фаза 3: Утверждение аналогов (HITL #1) ═══════════

    FE->>API: GET /api/session/{id}/analogs
    API->>LG: graph.get_state()
    API->>DATA: get_units_by_cte(), get_analog_stats()
    DATA-->>API: units_map, stats_map
    API-->>FE: SearchResponse {analogs, available_units}

    User->>FE: Выбрать аналоги ✓
    User->>FE: (опц.) Ввести CTE ID вручную
    User->>FE: (опц.) Добавить ручные цены
    User->>FE: Выбрать единицы измерения
    User->>FE: Нажать "Утвердить"

    FE->>API: POST /api/session/{id}/analogs/approve<br/>{approved_analog_ids, manual_cte_ids, units}
    API->>LG: graph.invoke(Command(resume=data))

    Note over LG,ML: ── Нода: process_prices ──

    LG->>DATA: get_prices_for_ctes(cte_ids, region, 12m, units)
    DATA-->>LG: Данные контрактов

    alt Нет цен по региону
        LG->>DATA: get_prices_for_ctes(cte_ids, ALL_REGIONS)
        alt Всё ещё нет цен
            LG->>DATA: get_prices_for_ctes(cte_ids, ALL, 24m)
        end
    end

    LG->>DATA: add_time_weights() → w = 1/(1+days/365)
    LG->>ML: IsolationForest.fit_predict(prices)
    ML-->>LG: Классификация: valid / outliers
    LG->>LG: interrupt() ⏸️

    LG-->>API: state + __interrupt__
    API-->>FE: {step: "waiting_for_price_approval"}

    Note over User,DOC: ═══════════ Фаза 4: Утверждение цен (HITL #2) ═══════════

    FE->>API: GET /api/session/{id}/prices
    API-->>FE: PricesResponse {filtered_prices, outlier_prices}

    FE->>API: GET /api/session/{id}/region-prices
    API->>DATA: get_region_price_stats(cte_ids, units)
    DATA-->>API: Статистика по регионам
    API-->>FE: RegionPricesResponse

    User->>FE: Просмотр PriceOptimizer (CV-анализ)
    User->>FE: Просмотр RegionHeatmap (карта)
    User->>FE: Убрать/добавить цены
    User->>FE: Нажать "Утвердить цены"

    FE->>API: POST /api/session/{id}/prices/approve<br/>{approved_price_indices, manual_prices}
    API->>LG: graph.invoke(Command(resume=data))

    Note over LG,DOC: ── Ноды: calculate_nmcc + generate_document ──

    LG->>ML: analyze_prices(approved_prices)
    ML-->>LG: {median, mean, cv, weighted_avg, is_homogeneous}
    LG->>LG: calculate_nmck()<br/>НМЦК_ед = base × К_инфл<br/>НМЦК = НМЦК_ед × qty

    LG->>DOC: generate_nmck_document()
    DOC-->>LG: Документ обоснования (.docx)
    LG-->>API: state {document_generated}

    API->>DB: Сохранение результатов расчёта
    API-->>FE: {step: "document_generated"}

    Note over User,DOC: ═══════════ Фаза 5: Результаты ═══════════

    FE->>API: GET /api/session/{id}/calculation
    API-->>FE: CalculationResponse {nmck, cv, homogeneous, ...}

    FE->>API: GET /api/purchase/{pid}/summary
    API-->>FE: PurchaseSummaryBoard {items, grand_total}

    User->>FE: Скачать документ
    FE->>API: GET /api/session/{id}/document
    API-->>FE: FileResponse (.docx)

    opt Консолидированный документ
        User->>FE: Скачать общий документ
        FE->>API: GET /api/purchase/{pid}/consolidated-document
        API->>DOC: generate_consolidated_document()
        DOC-->>API: Консолидированный .docx
        API-->>FE: FileResponse (.docx)
    end
```

---

## 5. Архитектура ML-пайплайна — Поиск и аналитика

```mermaid
flowchart LR
    subgraph "Индексация (при старте сервера)"
        CTE_DS["📦 Каталог СТЕ<br/>~350K+ позиций"]
        BATCH["Батчевая обработка<br/>256 позиций/батч"]
        PPLX_INDEX["🧠 Perplexity Embed v1<br/>pplx-embed-v1-0.6b<br/>Локальный инференс"]
        VECTORS["float[1024] × N"]
        UPSERT["Batch Upsert<br/>256 записей/батч"]
        QDRANT_STORE[("🔷 Qdrant<br/>cte_catalog<br/>Cosine Distance")]

        CTE_DS --> BATCH --> PPLX_INDEX --> VECTORS --> UPSERT --> QDRANT_STORE
    end

    subgraph "Поиск (runtime)"
        QUERY["🔤 Запрос пользователя<br/>название + категория"]
        PPLX_QUERY["🧠 Perplexity Embed v1<br/>encode_single()"]
        QUERY_VEC["float[1024]"]

        subgraph "Qdrant Search"
            COSINE["Косинусное<br/>сходство"]
            CAT_FILTER["Фильтр<br/>категории"]
            THRESHOLD["score ≥ 0.5"]
        end

        subgraph "Гибридное ранжирование"
            SEM_SCORE["Семантика<br/>вес: 50%"]
            KW_SCORE["Ключевые слова<br/>вес: 40%<br/>(word overlap)"]
            ATTR_SCORE["Атрибуты<br/>вес: 10%<br/>(characteristic match)"]
            CAT_BONUS["Бонус категории<br/>+5%"]
            FINAL_RANK["final_score =<br/>0.5×cosine +<br/>0.4×keyword +<br/>0.1×attr +<br/>0.05×cat_match"]
        end

        RESULTS["📋 Top-10<br/>аналогов"]

        QUERY --> PPLX_QUERY --> QUERY_VEC --> COSINE
        QUERY_VEC --> CAT_FILTER
        COSINE --> THRESHOLD
        CAT_FILTER --> THRESHOLD
        THRESHOLD --> SEM_SCORE
        THRESHOLD --> KW_SCORE
        THRESHOLD --> ATTR_SCORE
        THRESHOLD --> CAT_BONUS
        SEM_SCORE --> FINAL_RANK
        KW_SCORE --> FINAL_RANK
        ATTR_SCORE --> FINAL_RANK
        CAT_BONUS --> FINAL_RANK
        FINAL_RANK --> RESULTS
    end

    subgraph "Ценовая аналитика"
        PRICES_IN["💰 Цены контрактов"]

        subgraph "Предобработка"
            TIME_W["Временные веса<br/>w = 1/(1 + days/365)"]
            REGION_F["Фильтр региона"]
            UNIT_F["Фильтр ед. измерения"]
        end

        subgraph "IsolationForest (scikit-learn)"
            IF_MODEL["IsolationForest<br/>contamination='auto'"]
            IF_PREDICT["predict() → {valid, outlier}"]
            IF_REASON["Причина выброса:<br/>% отклонения от медианы"]
        end

        subgraph "Статистический анализ"
            MEDIAN["Медиана"]
            MEAN["Среднее"]
            STD_DEV["σ (std)"]
            CV_CALC["CV = (σ/μ) × 100%"]
            WAVG["Ц_avg = Σ(Цi×wi)/Σ(wi)"]
            HOMOG{"CV ≤ 33%?"}
        end

        PRICES_IN --> TIME_W --> REGION_F --> UNIT_F
        UNIT_F --> IF_MODEL --> IF_PREDICT --> IF_REASON
        IF_REASON --> MEDIAN
        IF_REASON --> MEAN
        IF_REASON --> STD_DEV
        MEDIAN --> CV_CALC
        MEAN --> CV_CALC
        STD_DEV --> CV_CALC
        MEAN --> WAVG
        CV_CALC --> HOMOG
    end

    style PPLX_INDEX fill:#FCE4EC,stroke:#C62828
    style PPLX_QUERY fill:#FCE4EC,stroke:#C62828
    style QDRANT_STORE fill:#E0F7FA,stroke:#00695C
    style IF_MODEL fill:#F3E5F5,stroke:#6A1B9A
    style HOMOG fill:#FFF9C4,stroke:#F57F17
```

---

## 6. Модель данных

```mermaid
erDiagram
    CTE_CATALOG ||--o{ CONTRACT : "Идентификатор СТЕ"
    PURCHASE ||--o{ CALCULATION : "purchase_id"
    CALCULATION ||--|| PIPELINE_STATE : "session_id"

    CTE_CATALOG {
        int id PK "Идентификатор СТЕ"
        string name "Наименование СТЕ"
        string category "Категория"
        string manufacturer "Производитель"
        json attributes "Характеристики (key-value)"
        vector embedding "Perplexity Embed v1 (1024-dim)"
    }

    CONTRACT {
        int id PK "Идентификатор контракта"
        int cte_id FK "Идентификатор СТЕ"
        float price_per_unit "Цена за единицу"
        float quantity "Количество"
        string unit "Единица измерения"
        date contract_date "Дата заключения контракта"
        string region "Регион заказчика"
        string supplier_inn "ИНН поставщика"
        string procurement_method "Способ закупки"
    }

    PURCHASE {
        int id PK "ID закупки"
        string region "Регион"
        string status "in_progress / completed"
        float total_nmck "Итого НМЦК"
        int items_count "Кол-во позиций"
        int completed_count "Завершённых"
        datetime created_at "Дата создания"
    }

    CALCULATION {
        int id PK "ID расчёта"
        int purchase_id FK "ID закупки"
        string session_id "ID сессии пайплайна"
        string cte_name "Наименование"
        string status "in_progress / completed"
        float nmck_per_unit "НМЦК за ед."
        float total_nmck "Итого НМЦК"
        float coefficient_of_variation "CV %"
        bool is_homogeneous "Однородность"
        int num_prices_used "Кол-во цен"
        string document_path "Путь к документу"
        json decisions "Решения пользователя"
        datetime created_at "Дата создания"
        datetime completed_at "Дата завершения"
    }

    PIPELINE_STATE {
        string session_id PK "ID сессии"
        string target_cte_name "Запрос"
        string region_filter "Регион"
        float quantity "Количество"
        json retrieved_analogs "Найденные аналоги"
        json user_approved_analogs "Утверждённые аналоги"
        json user_approved_prices "Утверждённые цены"
        float total_nmck "Итого НМЦК"
        string current_step "Текущий шаг"
        json justification "Обоснование"
    }

    QDRANT_COLLECTION {
        string collection_name "cte_catalog"
        int dimension "1024"
        string distance "Cosine"
    }
```

---

## 7. Диаграмма компонентов Frontend

```mermaid
flowchart TB
    subgraph "React Router DOM v7"
        ROUTER["🔀 BrowserRouter"]
    end

    subgraph "Layouts"
        HEADER["🧭 Header<br/>• Логотип<br/>• Навигация:<br/>  Новый расчёт | История"]
        TUTORIAL_BTN["❓ TutorialHelpButton<br/>Плавающая кнопка помощи"]
    end

    subgraph "Страница: / (CreatePurchasePage)"
        direction TB
        CP_REGION["🗺️ RegionSelector<br/>Автокомплит<br/>89 субъектов РФ"]
        CP_ROWS["📝 ItemSearchRow × N<br/>• Поиск СТЕ<br/>• Результаты с toggle<br/>• Добавить/удалить строку"]
        CP_RECENT["🕐 RecentPurchases<br/>Карусель последних закупок"]
        CP_SUBMIT["🚀 Кнопка 'Рассчитать НМЦК'<br/>→ navigate(/pipeline?...)"]

        CP_REGION --> CP_ROWS --> CP_SUBMIT
        CP_RECENT
    end

    subgraph "Страница: /pipeline (PipelineView)"
        direction TB
        PV_GRAPH["🔄 ReactFlow Graph<br/>5 этапов × N позиций<br/>Цветовые группы<br/>Статусы: ✅⏳🔵"]

        subgraph "Боковая панель (Inspector)"
            PV_ANALOGS["📋 Список аналогов<br/>• Выбор checkbox<br/>• Ручной ввод CTE ID<br/>• Ручной ввод цен<br/>• Выбор единиц"]
            PV_PRICES["💰 Таблица цен<br/>• Toggle включения<br/>• Флаги выбросов<br/>• Область поиска"]
            PV_CALC["🧮 Результат расчёта<br/>• НМЦК, CV%, однородность<br/>• Скачать .docx"]
        end

        PV_HEATMAP["🗺️ RegionHeatmap<br/>Интерактивная карта РФ<br/>Градиент: зелёный→красный<br/>Таблица с сортировкой"]
        PV_OPTIMIZER["📊 PriceOptimizer<br/>CV progress bar (33%)<br/>ML-рекомендации<br/>по оптимизации выборки"]
        PV_SUMMARY["📊 SummaryBoard<br/>Итоговая сводка<br/>Grand total + прописью"]

        PV_GRAPH --> PV_ANALOGS
        PV_GRAPH --> PV_PRICES
        PV_GRAPH --> PV_CALC
        PV_PRICES --> PV_HEATMAP
        PV_PRICES --> PV_OPTIMIZER
    end

    subgraph "Страница: /history (HistoryPage)"
        HP_LIST["📋 Список закупок<br/>Пагинация<br/>Группировка по времени"]
        HP_FILTER["🔍 Фильтр статуса<br/>Все | Завершённые | В процессе"]
        HP_ACTIONS["⚡ Действия:<br/>Открыть | Продолжить |<br/>Повторить | Удалить"]
    end

    subgraph "Страница: /history/:id (HistoryDetailPage)"
        HD_CARDS["📄 Карточки расчётов<br/>Развёрнутые/свёрнутые"]
        HD_METRICS["📊 Метрики:<br/>НМЦК | CV | Однородность"]
        HD_DOWNLOAD["⬇️ Скачать .docx"]
        HD_CONTINUE["▶️ Продолжить расчёт"]
    end

    subgraph "Контекст"
        TUTORIAL_CTX["🎓 TutorialProvider<br/>5 шагов обучающего тура"]
        TUTORIAL_OVL["🔦 TutorialOverlay<br/>Spotlight + Dialog"]
    end

    subgraph "API Client"
        API_CLIENT["📡 REST API Client<br/>• startSession()<br/>• getAnalogs()<br/>• approveAnalogs()<br/>• getPrices()<br/>• approvePrices()<br/>• getCalculation()<br/>• downloadDocument()<br/>• getRegionPrices()<br/>• createPurchase()<br/>• listPurchases()<br/>• getPurchaseSummary()"]
    end

    ROUTER --> HEADER
    ROUTER -->|"/"| CP_REGION
    ROUTER -->|"/pipeline"| PV_GRAPH
    ROUTER -->|"/history"| HP_LIST
    ROUTER -->|"/history/:id"| HD_CARDS
    TUTORIAL_CTX --> TUTORIAL_OVL
    TUTORIAL_BTN --> TUTORIAL_CTX
    API_CLIENT -.->|"HTTP"| CP_ROWS
    API_CLIENT -.->|"HTTP"| PV_GRAPH
    API_CLIENT -.->|"HTTP"| HP_LIST
    API_CLIENT -.->|"HTTP"| HD_CARDS

    style ROUTER fill:#E3F2FD,stroke:#1565C0
    style PV_GRAPH fill:#F3E5F5,stroke:#6A1B9A
    style PV_HEATMAP fill:#E8F5E9,stroke:#2E7D32
    style PV_OPTIMIZER fill:#FFF3E0,stroke:#E65100
    style API_CLIENT fill:#FFEBEE,stroke:#C62828
```

---

## 8. Диаграмма развёртывания (Docker)

```mermaid
flowchart TB
    subgraph "Docker Compose"
        subgraph "api-service"
            direction TB
            DOCKERFILE["🐳 Python 3.12<br/>Multi-stage build"]
            UVICORN["Uvicorn ASGI Server"]
            FASTAPI_APP["FastAPI Application"]

            subgraph "Предзагруженные модели"
                PPLX_MODEL["🧠 Perplexity Embed v1<br/>pplx-embed-v1-0.6b"]
            end

            subgraph "Данные"
                VOL_DATA["📦 База контрактов<br/>Каталог СТЕ"]
                VOL_OUTPUT["📄 Сгенерированные<br/>документы"]
            end

            DOCKERFILE --> UVICORN --> FASTAPI_APP
        end

        subgraph "qdrant-service"
            QDRANT_IMG["🔷 Qdrant"]
            QDRANT_REST["REST API"]
            QDRANT_GRPC["gRPC"]
            VOL_QDRANT["📦 Векторное<br/>хранилище"]

            QDRANT_IMG --> QDRANT_REST
            QDRANT_IMG --> QDRANT_GRPC
        end
    end

    subgraph "Клиент"
        BROWSER["🌐 Браузер<br/>(Frontend SPA)"]
    end

    BROWSER -->|"HTTP"| UVICORN
    FASTAPI_APP -->|"Внутренняя<br/>сеть Docker"| QDRANT_REST

    style DOCKERFILE fill:#E3F2FD,stroke:#1565C0
    style QDRANT_IMG fill:#E0F7FA,stroke:#00695C
    style BROWSER fill:#E8F5E9,stroke:#2E7D32
```

---

## 9. Формулы расчёта НМЦК (по Приказу Минэкономразвития №567)

```mermaid
flowchart TD
    subgraph "Входные данные"
        PRICES["Утверждённые цены<br/>Ц₁, Ц₂, ..., Цₙ"]
        WEIGHTS["Временные веса<br/>w₁, w₂, ..., wₙ<br/>wᵢ = 1/(1 + daysᵢ/365)"]
        QTY["Количество (V)"]
        INFL["Коэффициент инфляции (К)"]
    end

    subgraph "Шаг 1: Статистика"
        CALC_MEAN["Среднее:<br/>μ = Σ(Цᵢ) / n"]
        CALC_MEDIAN["Медиана:<br/>Me = sorted[n/2]"]
        CALC_STD["Стд. отклонение:<br/>σ = √(Σ(Цᵢ - μ)² / (n-1))"]
        CALC_CV["Коэф. вариации:<br/>CV = (σ / μ) × 100%"]
        CALC_WAVG["Средневзвешенная:<br/>Ц_avg = Σ(Цᵢ × wᵢ) / Σ(wᵢ)"]
    end

    subgraph "Шаг 2: Однородность"
        CHECK_CV{"CV ≤ 33%?"}
        HOMO_YES["✅ Однородная выборка<br/>Базовая цена = Ц_avg"]
        HOMO_NO["⚠️ Неоднородная выборка<br/>Базовая цена = Me"]
    end

    subgraph "Шаг 3: Расчёт НМЦК"
        NMCK_UNIT["НМЦК за единицу:<br/>НМЦК_ед = Ц_база × К"]
        NMCK_TOTAL["Итого НМЦК:<br/>НМЦК = НМЦК_ед × V"]
        PRICE_RANGE["Диапазон цен:<br/>min = НМЦК_ед × (1 - CV/100)<br/>max = НМЦК_ед × (1 + CV/100)<br/>(capped at ±50%)"]
    end

    PRICES --> CALC_MEAN --> CALC_CV
    PRICES --> CALC_MEDIAN
    PRICES --> CALC_STD --> CALC_CV
    WEIGHTS --> CALC_WAVG

    CALC_CV --> CHECK_CV
    CHECK_CV -->|"Да"| HOMO_YES
    CHECK_CV -->|"Нет"| HOMO_NO
    HOMO_YES --> NMCK_UNIT
    HOMO_NO --> NMCK_UNIT
    CALC_WAVG --> HOMO_YES
    CALC_MEDIAN --> HOMO_NO
    INFL --> NMCK_UNIT
    NMCK_UNIT --> NMCK_TOTAL
    QTY --> NMCK_TOTAL
    NMCK_UNIT --> PRICE_RANGE
    CALC_CV --> PRICE_RANGE

    style CHECK_CV fill:#FFF9C4,stroke:#F57F17
    style HOMO_YES fill:#C8E6C9,stroke:#2E7D32
    style HOMO_NO fill:#FFCDD2,stroke:#C62828
    style NMCK_TOTAL fill:#E3F2FD,stroke:#1565C0,stroke-width:3px
```

---

## 10. API Endpoints — полная карта

```mermaid
flowchart LR
    subgraph "REST API"
        subgraph "Сессии"
            EP1["POST /session/start<br/>→ SessionStatus"]
            EP2["GET /session/{id}/status<br/>→ SessionStatus"]
        end

        subgraph "Аналоги"
            EP3["GET /session/{id}/analogs<br/>→ SearchResponse"]
            EP4["POST /session/{id}/analogs/approve<br/>→ SessionStatus"]
            EP5["POST /session/{id}/analogs/reapprove<br/>→ SessionStatus"]
        end

        subgraph "Цены"
            EP6["GET /session/{id}/prices<br/>→ PricesResponse"]
            EP7["POST /session/{id}/prices/approve<br/>→ SessionStatus"]
            EP8["GET /session/{id}/region-prices<br/>→ RegionPricesResponse"]
        end

        subgraph "Расчёт"
            EP9["GET /session/{id}/calculation<br/>→ CalculationResponse"]
            EP10["GET /session/{id}/document<br/>→ FileResponse (.docx)"]
            EP11["POST /session/{id}/recalculate<br/>→ CalculationResponse"]
        end

        subgraph "Каталог СТЕ"
            EP12["GET /cte/{cte_id}/check<br/>→ {exists, name}"]
            EP13["GET /cte/search?q=<br/>→ {results}"]
        end

        subgraph "История закупок"
            EP14["POST /history<br/>→ {purchase_id}"]
            EP15["GET /history<br/>→ PurchaseListResponse"]
            EP16["GET /history/recent<br/>→ PurchaseListResponse"]
            EP17["GET /history/{id}<br/>→ PurchaseSummary"]
            EP18["DELETE /history/{id}"]
        end

        subgraph "Сводка закупки"
            EP19["GET /purchase/{id}/summary<br/>→ PurchaseSummaryBoard"]
            EP20["GET /purchase/{id}/consolidated-document<br/>→ FileResponse (.docx)"]
        end
    end

    subgraph "Потоки данных"
        LG_STATE["🔄 Pipeline State"]
        DB_HIST["💾 БД истории"]
        PL_DATA["📊 База контрактов"]
        QD_VEC["🔷 Qdrant"]
    end

    EP1 & EP4 & EP5 & EP7 -->|"invoke/resume"| LG_STATE
    EP2 & EP3 & EP6 & EP9 & EP10 -->|"get_state"| LG_STATE
    EP14 & EP15 & EP16 & EP17 & EP18 -->|"CRUD"| DB_HIST
    EP8 -->|"aggregate"| PL_DATA
    EP12 & EP13 -->|"search"| QD_VEC

    style EP1 fill:#C8E6C9,stroke:#2E7D32
    style EP4 fill:#FFECB3,stroke:#FF8F00
    style EP7 fill:#FFECB3,stroke:#FF8F00
    style EP10 fill:#BBDEFB,stroke:#1565C0
    style EP20 fill:#BBDEFB,stroke:#1565C0
```

---

## 11. Пользовательские потоки (User Journeys)

```mermaid
journey
    title Основной сценарий: Расчёт НМЦК
    section Создание закупки
        Открыть приложение: 5: Пользователь
        Выбрать регион: 4: Пользователь
        Ввести названия товаров: 4: Пользователь
        Поиск в каталоге СТЕ: 3: Система
        Отметить позиции: 4: Пользователь
        Нажать Рассчитать: 5: Пользователь
    section Поиск аналогов
        Векторизация запроса (Perplexity): 5: Система
        Поиск в Qdrant: 5: Система
        Гибридное ранжирование: 5: Система
        Показать аналоги: 4: Система
    section Утверждение аналогов
        Просмотр списка аналогов: 4: Пользователь
        Выбор подходящих: 4: Пользователь
        Добавить вручную (опц.): 3: Пользователь
        Утвердить аналоги: 5: Пользователь
    section Анализ цен
        Запрос контрактов: 5: Система
        Детекция выбросов: 5: Система
        Показать цены и карту: 4: Система
        Оптимизация CV: 3: Пользователь
        Утвердить цены: 5: Пользователь
    section Результат
        Расчёт НМЦК: 5: Система
        Генерация документа: 5: Система
        Просмотр результата: 5: Пользователь
        Скачать документ: 5: Пользователь
```

---

## 12. Fallback-стратегия поиска цен

```mermaid
flowchart TD
    START["Запрос цен контрактов<br/>CTE IDs + фильтры"]

    STEP1["Шаг 1: Поиск по РЕГИОНУ<br/>+ последние 12 месяцев<br/>+ фильтр единиц измерения"]
    CHECK1{"Найдены<br/>контракты?"}

    STEP2["Шаг 2: ВСЕ РЕГИОНЫ<br/>+ последние 12 месяцев<br/>+ фильтр единиц"]
    CHECK2{"Найдены<br/>контракты?"}

    STEP3["Шаг 3: ВСЕ РЕГИОНЫ<br/>+ расширенный период 24 мес<br/>+ фильтр единиц"]

    SCOPE1["scope = 'region'"]
    SCOPE2["scope = 'all_regions'"]
    SCOPE3["scope = 'all_regions_extended'"]

    RESULT["Продолжить с<br/>найденными данными"]

    START --> STEP1 --> CHECK1
    CHECK1 -->|"Да"| SCOPE1 --> RESULT
    CHECK1 -->|"Нет (и есть регион)"| STEP2 --> CHECK2
    CHECK2 -->|"Да"| SCOPE2 --> RESULT
    CHECK2 -->|"Нет"| STEP3 --> SCOPE3 --> RESULT

    style STEP1 fill:#C8E6C9,stroke:#2E7D32
    style STEP2 fill:#FFF9C4,stroke:#F57F17
    style STEP3 fill:#FFCDD2,stroke:#C62828
    style RESULT fill:#E3F2FD,stroke:#1565C0,stroke-width:3px
```

---

## 13. Алгоритм PriceOptimizer (Frontend)

```mermaid
flowchart TD
    INPUT["Входные цены<br/>[p₁, p₂, ..., pₙ]"]

    CALC_STATS["Расчёт CV текущей выборки<br/>CV = (σ / μ) × 100%"]

    CHECK_CV{"CV > 33%?"}

    OK["✅ Выборка однородна<br/>Оптимизация не требуется"]

    SUGGEST["Генерация рекомендаций<br/>по удалению"]

    subgraph "Скоринг каждой цены"
        SCORE_ML["ML-аномалия<br/>(is_outlier=true)<br/>+1000 баллов"]
        SCORE_EXTREME["Отклонение > 200%<br/>от медианы<br/>+500 баллов"]
        SCORE_HIGH["Отклонение > 100%<br/>от медианы<br/>+200 баллов"]
        SCORE_DEV["% отклонения<br/>от медианы<br/>+deviation баллов"]
        SCORE_CV["Влияние на CV<br/>при удалении<br/>+cv_reduction × 100"]
    end

    SORT["Сортировка по убыванию<br/>суммарного скора"]

    PREVIEW["Превью: если удалить<br/>top-K → новый CV = ?"]

    DISPLAY["Отображение:<br/>• Progress bar CV (порог 33%)<br/>• Список рекомендаций<br/>• Кнопка 'Удалить все'"]

    INPUT --> CALC_STATS --> CHECK_CV
    CHECK_CV -->|"Нет"| OK
    CHECK_CV -->|"Да"| SUGGEST
    SUGGEST --> SCORE_ML & SCORE_EXTREME & SCORE_HIGH & SCORE_DEV & SCORE_CV
    SCORE_ML & SCORE_EXTREME & SCORE_HIGH & SCORE_DEV & SCORE_CV --> SORT
    SORT --> PREVIEW --> DISPLAY

    style OK fill:#C8E6C9,stroke:#2E7D32
    style CHECK_CV fill:#FFF9C4,stroke:#F57F17
    style DISPLAY fill:#E3F2FD,stroke:#1565C0
```

---

## Используемые технологии (сводка)

| Слой | Технология | Назначение |
|------|-----------|------------|
| **Frontend** | React 19 + TypeScript | SPA-приложение |
| **Сборка** | Vite | Dev-сервер и бандлинг |
| **Стили** | Tailwind CSS | Утилитарный CSS |
| **Графы** | ReactFlow | Визуализация пайплайна |
| **Карты** | react-simple-maps | Тепловая карта регионов РФ |
| **Backend** | FastAPI + Uvicorn | REST API сервер |
| **Пайплайн** | LangGraph | Конечный автомат с HITL |
| **Эмбеддинги** | Perplexity Embed v1 (pplx-embed-v1-0.6b) | Локальная векторизация текста (1024-dim) |
| **Векторная БД** | Qdrant | Семантический поиск аналогов |
| **Аналитика данных** | Polars | Высокопроизводительная обработка контрактов |
| **ML** | scikit-learn (IsolationForest) | Детекция ценовых выбросов |
| **Контейнеризация** | Docker + Docker Compose | Развёртывание |
