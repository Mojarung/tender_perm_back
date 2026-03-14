# АРХИТЕКТУРА СИСТЕМЫ РАСЧЁТА НМЦК v4.0
**Проект:** Tender Hack Perm — Интеллектуальный калькулятор НМЦК
**Основано на:** Приказ Минэкономразвития №567 + анализ реальных данных

---

## 1. ФАКТЫ ИЗ ДАННЫХ

> Каждое решение ниже привязано к конкретному факту.

### 1.1. Масштабы

| Датасет | Записей | Размер |
|---------|---------|--------|
| `cte.json` (каталог СТЕ) | 244 492 | ~300 МБ |
| `contracts (2).json` (контракты) | 461 443 | ~200 МБ |
| Уникальных контрактов | 100 468 | — |
| Пересечение CTE ↔ Контракты | 244 241 (99.9%) | Почти полное |

### 1.2. Критические паттерны

| Факт | Число | Что значит |
|------|-------|------------|
| СТЕ с 1 контрактом | 174 870 (71.6%) | **Большинству нужен поиск аналогов** |
| СТЕ с 2–5 контрактами | 60 537 (24.8%) | Может хватить, может нет |
| СТЕ с 6+ контрактами | 8 917 (3.6%) | Достаточно данных |
| 5 311 категорий | — | Фильтр по категории сужает поиск |
| 95 031 уникальных ключей характеристик | — | Нельзя захардкодить — слишком разнообразно |
| 4 944 дублей имён (разные ID) | — | "Очки защитные" x18 — имя одно, товары разные |
| 10 СТЕ без характеристик | — | Минорно |

### 1.3. Регионы

| Регион | Записей | % от всех | Месяцев |
|--------|---------|-----------|---------|
| Москва | 412 977 | 89.5% | 12 |
| Пермский край | 39 979 | 8.7% | 12 |
| Ямало-Ненецкий АО | 6 720 | 1.5% | 12 |
| Псковская область | 1 397 | 0.3% | 12 |
| Остальные 10 | 370 | <0.1% | 1–11 |

**Вывод:** Реально работают 3 региона: Москва, Пермский край, ЯНАО. Остальные — единичные записи. "Сургут" указан как регион, но это город в ХМАО — **аномалия в данных**.

### 1.4. Даты

Все данные за **12 месяцев**: январь — декабрь 2025. Равномерное распределение (22–53K/мес).

### 1.5. Цены

| Показатель | Значение |
|-----------|----------|
| Минимальная | 0.01 руб |
| Медиана | 562 руб |
| Средняя | 6 701 руб |
| Максимальная | 27 500 000 руб |
| Цена < 1 руб | 1 166 (0.25%) |
| Цена > 1M руб | 133 (0.03%) |
| qty = 0 | 9 729 записей |

### 1.6. НДС

| Ставка | Записей |
|--------|---------|
| Без НДС | 255 991 (55.5%) |
| 20% | 105 962 (23.0%) |
| 10% | 78 135 (16.9%) |
| 5% | 16 913 (3.7%) |
| 0% | 3 175 (0.7%) |
| 22%, 7% | 1 267 (<0.3%) |

29 930 СТЕ имеют смешанные ставки. Проверка: для одного товара ratio цена_с_НДС / цена_без_НДС ≈ 0.94–1.04 (а не 1.20). **Вывод: поле "Цена за единицу" — это уже итоговая цена, нормализация НДС НЕ нужна.**

### 1.7. Единицы измерения

| Единица | % |
|---------|---|
| шт | 76.8% |
| упак | 11.3% |
| кг | 2.2% |
| пар | 1.9% |
| набор / компл | 3.3% |
| остальные | 4.5% |

**571 СТЕ имеют смешанные единицы** в разных контрактах (шт vs упак). При сравнении цен — **фильтровать по единице обязательно**.

### 1.8. Межрегиональная разница цен

- Медианная разница между регионами для одного товара: **37.4%**
- 66.2% товаров в 2+ регионах отличаются на >20%

### 1.9. Однородность цен (коэффициент вариации)

Для СТЕ с 3+ ценами (32 230 штук):
- CV ≤ 33% (однородные): **73.5%**
- CV > 33% (неоднородные): **26.5%**
- CV > 100% (сильно разбросанные): **2.1%**

### 1.10. Скидки

- 73.1% контрактов имеют снижение цены от начальной
- Медианная скидка: 19%
- Максимальная: 99.99%

---

## 2. ОЧИСТКА ДАННЫХ (ПОДРОБНО)

### 2.1. Очистка CTE каталога (cte.json)

```
Шаг 1: Загрузка JSON
  └── json.load() → list[dict], 244 492 записи

Шаг 2: Конвертация характеристик
  └── "характеристики СТЕ": [["ключ","значение"], ...] → dict[str, str]
  └── Убираем пары с пустым value ("") → 357 штук
  └── Значения "0.00000" → оставляем, но помечаем (40 457, 1.7%)
      Причина: "Длина: 0.00000" может быть битым, а "Минимальная рабочая
      температура: 0.00000" — валидным

Шаг 3: Нормализация имён
  └── strip() пробелов, табуляций (5 записей с \t\n)
  └── Замена множественных пробелов → один пробел
  └── Удаление HTML entities (& < >) → 810 записей
  └── НЕ обрезаем длинные имена (max 5318 символов) —
      обрезка будет на этапе эмбеддинга

Шаг 4: Парсинг числовых данных из названий
  └── Зачем: "Мусорные пакеты 35л" — объём 35 есть в имени,
      но НЕ ВСЕГДА есть в характеристиках (у "Пакеты для мусора"
      характеристика "Объем: 30" есть, а у "ЗИП-пакеты 25смх30см"
      размеры только в имени)
  └── Regex: r'(\d+[\.,]?\d*)\s*(л|мл|мм|см|м|кг|г|шт|мкм|%)'
  └── Результат сохраняем как доп. поле parsed_from_name: dict
  └── НЕ перезаписываем характеристики — это fallback-данные

Шаг 5: Результат
  └── Каждая запись CTE:
      {
        cte_id: int,
        name: str,              # очищенное
        category: str,
        manufacturer: str,
        characteristics: dict,  # конвертированное из [[k,v],...]
        parsed_from_name: dict, # {"л": 35, "мм": 25} и т.д.
        raw_name: str           # оригинальное имя
      }
```

### 2.2. Очистка контрактов (contracts.json)

```
Шаг 1: Загрузка
  └── Polars pl.read_json() → DataFrame, 461 443 строки

Шаг 2: Фильтрация мусора
  ├── Удалить qty == 0 → -9 729 строк
  ├── Удалить price < 0.01 → 0 строк (нет отрицательных)
  ├── Пометить price < 1 руб как "suspicious" (не удалять) → 1 166
  ├── Пометить price > 1M руб как "expensive" (не удалять) → 133
  └── Удалить полные дубликаты (contract_id + cte_id + price) → -799 строк

Шаг 3: Приведение типов
  ├── "Дата заключения контракта" → Datetime (формат "%Y-%m-%d %H:%M:%S.%f")
  ├── "Цена за единицу" → Float64
  ├── "Количество" → Float64
  ├── "% снижения" → Float64
  └── Новый столбец: "Месяц" = date.dt.strftime("%Y-%m")

Шаг 4: Очистка имён позиций
  └── 2 записи содержат _x000D_ (Windows carriage return в данных)
  └── strip + замена \r\n → пробел

Шаг 5: Нормализация регионов
  └── "Сургут" → "Ханты-Мансийский автономный округ" (41 запись)
  └── Причина: Сургут — город в ХМАО, но указан как регион

Шаг 6: Результат
  └── Чистый DataFrame: ~450 900 строк (после фильтрации)
  └── Столбцы: оригинальные + "Месяц" + "suspicious_price" + "expensive_price"
```

---

## 3. ФОРМИРОВАНИЕ ЭМБЕДДИНГОВ (ПОДРОБНО)

### 3.1. Проблема: почему нельзя эмбедить только имя

Примеры из реальных данных (категория "Пакеты полимерные", 288 товаров):

```
Товар 1: "Мусорные пакеты 35л"   → Объем: 35,  Толщина: 50 мкм,  Цена ~85 руб
Товар 2: "Мусорные пакеты 240л"  → Объем: 240, Толщина: 100 мкм, Цена ~350 руб
Товар 3: "Пакеты для мусора"     → Объем: 30,  нет толщины,       Цена ~70 руб

Cosine similarity("Мусорные пакеты 35л", "Мусорные пакеты 240л") ≈ 0.95
Цена отличается в 4 раза!
```

Другой пример (категория "Ручки канцелярские", 1 182 товара):
```
"Ручка шариковая Berlingo Tribase grip orange черная 0,5 мм" → 15 характеристик
"Ручка гелевая Berlingo Velvet цвет чернил синий"           → 6 характеристик

Названия похожи, но тип (шариковая vs гелевая) критичен для цены.
```

### 3.2. Стратегия формирования текста

```python
def build_embedding_text(item: dict) -> str:
    """
    3 слоя информации, каждый добавляет различающую способность.
    """
    # СЛОЙ 1: Имя + Категория (всегда есть)
    parts = [item["name"], item["category"]]

    # СЛОЙ 2: Приоритетные характеристики
    # Отобраны по частоте в данных (top-14 из 95 031 ключей):
    #   Вид товаров: 102K, Вид продукции: 100K, Цвет: 80K,
    #   Материал: 45K, Длина: 42K, Вес: 41K, Ширина: 38K,
    #   Назначение: 31K, Высота: 27K, Тип: 20K, Размер: 18K,
    #   Диаметр: 16K, Объем: 16K, Кол-во в упаковке: 15K
    PRIORITY_KEYS = [
        "Вид товаров", "Вид продукции", "Назначение", "Тип",
        "Материал", "Объем", "Размер", "Вес",
        "Длина", "Ширина", "Высота", "Диаметр",
        "Количество в упаковке", "Цвет",
    ]

    chars = item["characteristics"]
    for key in PRIORITY_KEYS:
        val = chars.get(key)
        if val and val != "0.00000":  # фильтруем нулевые (40K случаев)
            parts.append(f"{key}: {val}")

    # СЛОЙ 3: Остальные характеристики (до 10 штук, чтобы не раздувать)
    remaining = [
        (k, v) for k, v in chars.items()
        if k not in PRIORITY_KEYS and v and v != "0.00000"
    ]
    for k, v in remaining[:10]:
        parts.append(f"{k}: {v}")

    text = " | ".join(parts)

    # Обрезка: pplx-embed имеет лимит токенов.
    # Средняя длина имени 59 символов + категория + ~15 характеристик
    # → обычно 200-400 символов. Обрезаем если > 1000 символов.
    return text[:1000]
```

### 3.3. Примеры сформированных текстов

```
IN:  CTE 34863000 "Мусорные пакеты 35л"
OUT: "Мусорные пакеты 35л | Пакеты полимерные | Объем: 35.00000 |
      Количество в упаковке: 30.00000 | Цвет: черный |
      Толщина, мкм: 50.00000 | Вид материала: ПВД"

IN:  CTE 34865337 "Мусорные пакеты 240л"
OUT: "Мусорные пакеты 240л | Пакеты полимерные | Объем: 240.00000 |
      Количество в упаковке: 10.00000 | Цвет: черный |
      Толщина, мкм: 100.00000 | Вид материала: ПВД"

Теперь cosine similarity между ними будет ниже, потому что
"Объем: 35" vs "Объем: 240" создаёт расхождение в эмбеддинге.
```

### 3.4. Загрузка в Qdrant

```
Collection: cte_catalog
  Vector: float[] (размерность модели pplx-embed-v1-0.6b)
  Distance: Cosine
  Payload:
    cte_id:          int        # 34863000
    name:            str        # "Мусорные пакеты 35л"
    category:        str        # "Пакеты полимерные"
    manufacturer:    str        # "ООО СПРИНТ-ПЛАСТ"
    characteristics: dict       # {"Объем": "35.00000", ...}
    embedding_text:  str        # полный текст (для дебага)
    unit_hints:      list[str]  # единицы из контрактов для этого CTE

Batch upsert: 244 492 записей, батчами по 1000.
На pplx-embed 0.6B (CPU): ~2-4 часа при первом запуске.
Кэшируется в Qdrant volume — повторный запуск мгновенный.
```

---

## 4. ПОИСК АНАЛОГОВ (4 ЭТАПА + RE-RANKING)

### Общая схема

```
Пользователь вводит: "Мусорные пакеты 35л", qty=100, unit=упак, region=Пермский край
                              │
         ┌────────────────────┼─────────────────────┐
         ▼                    ▼                      ▼
    Этап 1               Этап 2                  Этап 3
    Exact match          Категория +              Qdrant
    по CTE ID            характеристики           semantic search
         │                    │                      │
         └────────────────────┼──────────────────────┘
                              ▼
                      Объединение + дедупликация
                              │
                              ▼
                      RE-RANKING (§4.6)
                              │
                              ▼
                      Проверка: набралось ≥3 с ценами?
                        │ НЕТ           │ ДА
                        ▼               ▼
                   Этап 4:         → К расчёту цен
                   Расширенный
                   поиск
                        │
                        ▼
                   Human-in-the-Loop
```

### 4.1. Этап 1 — Точное совпадение по CTE ID

```
Когда: пользователь указал конкретный CTE ID или система нашла точное совпадение
Что:   SELECT * FROM contracts WHERE cte_id = target_cte_id
Результат: список цен для ЭТОГО ЖЕ товара

71.6% СТЕ имеют только 1 контракт → обычно недостаточно.
Даже если нашли — всё равно ищем аналоги, чтобы дать пользователю выбор.
Но эти цены идут с пометкой source="exact" и имеют наивысший приоритет.
```

### 4.2. Этап 2 — Поиск по категории + характеристикам

```
Зачем: Структурированный поиск — надёжный, предсказуемый.
       97.5% товаров с 1 контрактом находятся в категориях с >5 товарами.

Алгоритм:
  1. Взять category целевого товара из CTE каталога
  2. Отфильтровать все CTE с той же category
     └── Размер выборки: от 1 до 8 664 товаров (медиана ~20)
  3. Для каждого кандидата вычислить match_score по характеристикам
  4. Отсортировать по match_score DESC
  5. Вернуть top-20
```

### 4.3. Алгоритм match_score (подробно)

```python
def match_score(
    target: dict,       # characteristics целевого товара
    candidate: dict,    # characteristics кандидата
    target_parsed: dict # parsed_from_name целевого товара
) -> tuple[float, dict]:
    """
    Возвращает (score 0.0–1.0, детали совпадений)
    """
    matches = {}
    score = 0.0
    weight_sum = 0.0

    # Веса для разных типов характеристик
    WEIGHTS = {
        "Объем": 3.0,      # объём критичен (35л vs 240л)
        "Вес": 2.0,
        "Размер": 2.0,
        "Материал": 2.5,   # ПВД vs полиэтилен = разная цена
        "Тип": 2.5,
        "Назначение": 2.0,
        "Вид товаров": 2.0,
        "Вид продукции": 2.0,
        "_default": 1.0,
    }

    for key, target_val in target.items():
        if target_val == "0.00000" or not target_val:
            continue

        w = WEIGHTS.get(key, WEIGHTS["_default"])
        weight_sum += w

        if key not in candidate:
            matches[key] = {"status": "missing", "score": 0}
            continue

        cand_val = candidate[key]

        # Попытка числового сравнения
        try:
            t_num = float(target_val.replace(",", "."))
            c_num = float(cand_val.replace(",", "."))

            if t_num == 0:
                continue  # пропускаем нулевые

            ratio = abs(c_num - t_num) / t_num

            if ratio <= 0.10:      # ±10% → полное совпадение
                s = 1.0
            elif ratio <= 0.30:    # ±30% → частичное
                s = 1.0 - (ratio - 0.10) / 0.20 * 0.5  # 1.0→0.5
            elif ratio <= 0.50:    # ±50% → слабое
                s = 0.5 - (ratio - 0.30) / 0.20 * 0.5  # 0.5→0.0
            else:
                s = 0.0

            score += s * w
            matches[key] = {
                "status": "numeric",
                "target": t_num, "candidate": c_num,
                "diff_pct": round(ratio * 100, 1),
                "score": round(s, 2)
            }
        except ValueError:
            # Строковое сравнение
            t_norm = target_val.lower().strip()
            c_norm = cand_val.lower().strip()

            if t_norm == c_norm:
                s = 1.0
            elif t_norm in c_norm or c_norm in t_norm:
                s = 0.7  # частичное совпадение ("ПВД" in "Полиэтилен высокого давления")
            else:
                s = 0.0

            score += s * w
            matches[key] = {
                "status": "string",
                "target": target_val, "candidate": cand_val,
                "score": round(s, 2)
            }

    final_score = score / weight_sum if weight_sum > 0 else 0.0

    return round(final_score, 3), matches
```

### 4.4. Этап 3 — Семантический поиск (Qdrant)

```
Зачем: Находит товары, которые Этап 2 пропускает:
  - Товары с другой формулировкой ("Мешки для мусора" vs "Мусорные пакеты")
  - Товары из смежных категорий
  - Товары, у которых мало заполненных характеристик

Алгоритм:
  1. Формируем embedding_text для целевого товара (§3.2)
  2. Encode через pplx-embed → вектор
  3. Qdrant search:
     - top_k = 50
     - filter: category == target.category (payload filter Qdrant)
     - score_threshold: 0.70
  4. Результат: список (cte_id, cosine_score, payload)

Важно: Qdrant filter по категории делается на стороне Qdrant (не post-filter),
это быстро даже при 244K записей.
```

### 4.5. Этап 4 — Расширенный поиск (fallback)

```
Когда: после этапов 1–3 нашлось < 3 CTE с ценами в контрактах
Что:
  1. Qdrant search БЕЗ фильтра по категории, top_k=100
  2. score_threshold: 0.80 (выше порог, т.к. без категории)
  3. Пометка: source="extended", confidence="low"

Если всё равно < 3:
  → Ручной ввод цены пользователем (source="manual")
```

### 4.6. Re-ranking (объединение всех этапов)

```
Все кандидаты из этапов 1–4 объединяются.
Дедупликация по cte_id.

Для каждого кандидата:
  combined_score = cosine_score × 0.3 + char_match_score × 0.5 + source_bonus × 0.2

  source_bonus:
    exact    → 1.0
    category → 0.8
    semantic → 0.6
    extended → 0.3
    manual   → 1.0

Дополнительные фильтры (жёсткие, НЕ влияют на score):
  ✗ Убрать кандидатов с другой единицей измерения (шт ≠ упак ≠ кг)
    └── Единицу берём из контрактов для данного CTE
    └── 571 CTE имеют смешанные единицы → берём самую частую для CTE
  ✗ Убрать кандидатов без цен в контрактах (нет смысла показывать аналог,
    по которому нет ценовой информации)

Результат: top-20 кандидатов, отсортированных по combined_score.
Отдаём пользователю в UI для подтверждения/редактирования.
```

---

## 5. РЕГИОНЫ (ПОДРОБНО)

### 5.1. Проблема

Данные перекошены: 89.5% — Москва. Если пользователь из Перми, у него будет мало "своих" цен. При этом цены между регионами отличаются на 37.4% (медиана).

### 5.2. Стратегия каскадного расширения

```
Пользователь указывает: region = "Пермский край"

Каскад 1: ТОЧНЫЙ РЕГИОН
  └── Фильтр: "Регион заказчика" == "Пермский край"
  └── Проверка: набралось ≥ 3 цен?
       │ ДА → используем только региональные, помечаем "Региональные цены"
       │ НЕТ ↓

Каскад 2: ФЕДЕРАЛЬНЫЙ УРОВЕНЬ (все регионы)
  └── Фильтр: без фильтра по региону
  └── Помечаем каждую цену тегом региона
  └── В UI: региональные цены подсвечены зелёным, другие — серым
  └── Проверка: набралось ≥ 3?
       │ ДА → используем все, помечаем "Федеральные цены"
       │ НЕТ ↓

Каскад 3: РУЧНОЙ ВВОД
  └── Предлагаем пользователю ввести цену вручную
```

### 5.3. Нормализация названий регионов

```python
REGION_NORMALIZE = {
    "Сургут": "Ханты-Мансийский автономный округ",
    # Если появятся другие аномалии — добавлять сюда
}
```

### 5.4. Региональный коэффициент (опционально)

```
Если все цены из Москвы, а пользователь из Перми:
  Из данных: средняя цена Москвы (median=581.90) vs Пермь (median=400.00)
  Ratio ≈ 0.69

  Но это грубая оценка. Для хакатона — НЕ применяем автоматический
  коэффициент. Вместо этого показываем пользователю:
  "⚠ Цены взяты из других регионов (Москва). Цены в Пермском крае
   могут отличаться на ~30%."
```

---

## 6. ФИЛЬТРАЦИЯ И РАНЖИРОВАНИЕ ЦЕН

### 6.1. Сбор цен

```
Input: approved_cte_ids (подтверждённые пользователем аналоги)
       target_region
       target_unit

Polars запрос:
  contracts_df
    .filter(col("Идентификатор СТЕ по контракту").is_in(approved_cte_ids))
    .filter(col("Количество") > 0)
    .filter(col("Цена за единицу") >= 0.01)
    .filter(col("Единица измерения") == target_unit)  # ОБЯЗАТЕЛЬНО

  Затем каскадный фильтр по региону (§5.2)
```

### 6.2. Фильтр по давности + коэффициент-дефлятор

По **Приказу 567 Минэкономразвития**: если цена получена ранее, чем за 6 месяцев до дня расчёта НМЦК, применяется **коэффициент пересчёта kd**.

Формула из приказа:
```
kd = ∏(Iτ / 100)  для τ от τ₀ до t

где Iτ = индекс потребительских цен месяца τ к предыдущему месяцу
```

Для хакатона (нет доступа к ИПЦ Росстата, оффлайн):

```
Упрощённый подход:
  - Свежие (≤ 6 мес от "сейчас"):   kd = 1.0, используем как есть
  - Старые (6–12 мес):              kd = 1.05 (условная инфляция ~5%)
  - Очень старые (> 12 мес):        отсечение

Пересчитанная цена = Цена_исходная × kd

В документе обоснования указываем:
  "Цена скорректирована с учётом коэффициента пересчёта kd=1.05
   (контракт от [дата], давность > 6 месяцев)"
```

Реализация:
```python
from datetime import datetime, timedelta

def apply_time_adjustment(
    price: float,
    contract_date: datetime,
    calculation_date: datetime
) -> tuple[float, float, str]:
    """
    Returns: (adjusted_price, kd, justification)
    """
    months_ago = (calculation_date - contract_date).days / 30.44

    if months_ago <= 6:
        return price, 1.0, "Актуальная цена (давность ≤ 6 мес.)"
    elif months_ago <= 12:
        kd = 1.05
        return price * kd, kd, f"Пересчёт kd={kd} (давность {months_ago:.0f} мес.)"
    else:
        return 0, 0, "Отсечено: давность > 12 месяцев"
```

### 6.3. Обработка выбросов (IQR)

```
Зачем IQR:
  1. Прозрачен — формулу можно записать в документ
  2. По приказу 567: если CV > 33% → пересмотр выборки.
     IQR делает именно это — убирает экстремальные значения.
  3. Стабилен при малых выборках (от 4 значений)
  4. В данных: 26.5% товаров имеют CV > 33%, им нужна очистка

Алгоритм:
  1. Сортировка цен
  2. Q1 = 25-й перцентиль, Q3 = 75-й перцентиль
  3. IQR = Q3 - Q1
  4. Допустимый диапазон: [Q1 - 1.5×IQR, Q3 + 1.5×IQR]
  5. Всё, что вне — выброс

  Если после IQR < 3 цен:
    → Мягкий IQR (коэффициент 2.5 вместо 1.5)
    → Если всё ещё < 3 → вернуть все + WARNING

Для документа обоснования формируем текст:
  "Фильтрация выбросов методом межквартильного размаха:
   Q1={q1:.2f} руб, Q3={q3:.2f} руб, IQR={iqr:.2f} руб.
   Допустимый диапазон: [{lower:.2f}, {upper:.2f}] руб.
   Отсечено {n_outliers} из {n_total} ценовых значений."
```

### 6.4. Итоговый пайплайн фильтрации

```
raw_prices (из контрактов)
    │
    ▼
Фильтр: qty > 0, price ≥ 0.01 ─────────── удаляем мусор
    │
    ▼
Фильтр: единица измерения == target_unit ── сравниваем только одинаковые
    │
    ▼
Каскадный фильтр по региону (§5.2) ──────── приоритет своему региону
    │
    ▼
Пересчёт давности: kd (§6.2) ──────────── старые цены индексируем
    │
    ▼
IQR outlier detection (§6.3) ──────────── убираем экстремальные
    │
    ▼
Проверка: ≥ 3 цены?
    │ НЕТ → мягкий IQR или всё + WARNING
    │ ДА ↓
    ▼
→ Human-in-the-Loop: пользователь видит таблицу цен,
  выбросы помечены, может добавить/убрать/ввести вручную
```

---

## 7. РАСЧЁТ НМЦК (по Приказу 567 Минэкономразвития)

Источник: [Приказ Минэкономразвития от 02.10.2013 №567](https://www.consultant.ru/document/cons_doc_LAW_153376/d5c20eb2e2498725630832953e0f9bd9fd28bf22/)

### 7.1. Формулы

```
Дано:
  Цᵢ — цена единицы товара из i-го источника (после пересчёта kd)
  n  — количество используемых цен (минимум 3)
  v  — количество закупаемых единиц

Шаг 1. Средняя арифметическая цена:
  ⟨Ц⟩ = (1/n) × Σ Цᵢ                            (i = 1..n)

Шаг 2. Среднеквадратичное отклонение:
  σ = √[ (1/n) × Σ (Цᵢ - ⟨Ц⟩)² ]              (i = 1..n)

Шаг 3. Коэффициент вариации:
  V = (σ / ⟨Ц⟩) × 100%

Шаг 4. Проверка однородности:
  V ≤ 33%  →  данные однородны, расчёт валиден
  V > 33%  →  данные неоднородны:
              "Целесообразно провести дополнительные исследования
               в целях увеличения количества ценовой информации"
              → UI предлагает: изменить выборку аналогов / убрать выбросы

Шаг 5. Итоговая НМЦК:
  НМЦК = v × ⟨Ц⟩

  С коэффициентами коррекции (если есть):
  НМЦК = v × (1/n) × Σ (Цᵢ × kᵢ)
  где kᵢ — коэффициент (для нас это kd из §6.2)
```

**ВАЖНО:** Приказ 567 использует **простое среднее арифметическое**, а не медиану и не взвешенное. Мы следуем приказу.

### 7.2. Реализация

```python
import math

def calculate_nmcc(
    prices: list[float],    # Цены после пересчёта kd
    quantity: float,        # Количество единиц
) -> dict:
    n = len(prices)
    if n < 1:
        return {"error": "Нет ценовых данных"}

    # Среднее арифметическое ⟨Ц⟩
    mean_price = sum(prices) / n

    # Среднеквадратичное отклонение σ
    variance = sum((p - mean_price) ** 2 for p in prices) / n
    sigma = math.sqrt(variance)

    # Коэффициент вариации V
    cv = (sigma / mean_price * 100) if mean_price > 0 else 0

    # НМЦК
    nmcc = mean_price * quantity

    return {
        "mean_price": round(mean_price, 2),
        "sigma": round(sigma, 2),
        "cv_percent": round(cv, 2),
        "is_homogeneous": cv <= 33,
        "nmcc": round(nmcc, 2),
        "prices_used": n,
        "quantity": quantity,
        "interpretation": (
            "Однородная выборка" if cv <= 10
            else "Средняя вариация" if cv <= 20
            else "Значительная вариация" if cv <= 33
            else "НЕОДНОРОДНАЯ ВЫБОРКА — требуется пересмотр"
        ),
    }
```

### 7.3. Что показываем пользователю после расчёта

```
┌─────────────────────────────────────────────────────────┐
│  РЕЗУЛЬТАТ РАСЧЁТА НМЦК                                │
├─────────────────────────────────────────────────────────┤
│  Товар: Мусорные пакеты 35л                            │
│  Количество: 100 упак                                  │
│  Регион: Пермский край                                 │
│                                                         │
│  Средняя цена за единицу: 85.75 руб                    │
│  Среднеквадратичное отклонение: 4.23 руб               │
│  Коэффициент вариации: 4.93% ✅ (< 33%)               │
│                                                         │
│  ═══════════════════════════════                        │
│  НМЦК = 85.75 × 100 = 8 575.00 руб                    │
│  ═══════════════════════════════                        │
│                                                         │
│  Использовано источников: 4                            │
│  Отсечено выбросов: 1                                  │
│  Метод: сопоставимых рыночных цен (Приказ 567)         │
│                                                         │
│  [Подтвердить]  [Пересчитать]  [Изменить аналоги]      │
└─────────────────────────────────────────────────────────┘
```

---

## 8. LangGraph STATE MACHINE

### 8.1. Состояние

```python
from pydantic import BaseModel, Field

class AnalogItem(BaseModel):
    cte_id: int
    name: str
    category: str
    cosine_score: float          # от Qdrant (0–1)
    char_match_score: float      # от match_score (0–1)
    combined_score: float        # итоговый (0–1)
    source: str                  # "exact"|"category"|"semantic"|"extended"|"manual"
    match_details: dict          # подробности совпадения характеристик

class PriceRecord(BaseModel):
    cte_id: int
    cte_name: str
    price_original: float        # исходная цена
    price_adjusted: float        # после пересчёта kd
    kd: float                    # коэффициент пересчёта
    date: str
    region: str
    contract_id: int
    vat_rate: str
    quantity: float
    unit: str
    is_outlier: bool = False
    is_regional: bool = False    # из целевого региона?
    source: str                  # "contract"|"manual"

class NMCCResult(BaseModel):
    mean_price: float
    sigma: float
    cv_percent: float
    is_homogeneous: bool
    nmcc: float
    prices_used: int
    quantity: float
    interpretation: str

class PipelineState(BaseModel):
    session_id: str

    # Input
    target_cte_id: int | None = None
    target_cte_name: str = ""
    target_quantity: float = 1.0
    target_unit: str = "шт"
    target_region: str | None = None

    # Step 1-4: Analog search
    found_analogs: list[AnalogItem] = Field(default_factory=list)
    user_approved_analogs: list[AnalogItem] = Field(default_factory=list)

    # Step 5-6: Price collection
    all_prices: list[PriceRecord] = Field(default_factory=list)
    valid_prices: list[PriceRecord] = Field(default_factory=list)
    outlier_prices: list[PriceRecord] = Field(default_factory=list)
    outlier_justification: str = ""
    user_approved_prices: list[PriceRecord] = Field(default_factory=list)

    # Step 7: NMCC
    nmcc_result: NMCCResult | None = None

    # Step 8: Document
    document_path: str | None = None

    current_step: str = "init"
    region_fallback_used: bool = False    # были ли использованы федеральные цены
    errors: list[str] = Field(default_factory=list)
```

### 8.2. Граф и переходы

```
  ┌──────────┐
  │   init   │
  └────┬─────┘
       │
       ▼
  ┌──────────────┐
  │search_analogs│  Этапы 1→2→3→(4)
  └────┬─────────┘
       │
       ▼
  ┌──────────────────┐         ┌──────────────────┐
  │wait_analog_approv│◄────────│  (пользователь   │
  │  (INTERRUPT)     │────────►│   утвердил)      │
  └────┬─────────────┘         └──────────────────┘
       │
       ▼
  ┌──────────────┐
  │ fetch_prices │  Polars: CTE IDs → цены, фильтры
  └────┬─────────┘
       │
       ▼
  ┌────────────────┐
  │filter_outliers │  IQR + kd + region cascade
  └────┬───────────┘
       │
       ▼
  ┌──────────────────┐         ┌──────────────────┐
  │wait_price_approv │◄────────│  (пользователь   │
  │  (INTERRUPT)     │────────►│   утвердил/      │
  └────┬─────────────┘         │   ввёл вручную)  │
       │                       └──────────────────┘
       ▼
  ┌──────────────┐
  │calculate_nmcc│  Формулы §7
  └────┬─────────┘
       │
       ▼
  ┌──────────────────┐         ┌──────────────────┐
  │wait_calc_approv  │◄────────│  CV > 33%?       │
  │  (INTERRUPT)     │────────►│  Подтвердить /   │
  └────┬─────────────┘         │  вернуться       │
       │                       └──────────────────┘
       ▼
  ┌────────────────┐
  │generate_doc    │  docxtpl → .docx
  └────┬───────────┘
       │
       ▼
  ┌──────┐
  │ END  │
  └──────┘

Обратные переходы:
  wait_price_approv  ──back──► wait_analog_approv  (поменять аналоги)
  wait_calc_approv   ──back──► wait_price_approv   (поменять цены)
  wait_calc_approv   ──back──► wait_analog_approv  (поменять всё)
```

---

## 9. API ENDPOINTS

```
POST   /api/sessions
       Body: { target_cte_name, target_cte_id?, target_quantity,
               target_unit, target_region? }
       Response: { session_id, current_step, found_analogs[] }

GET    /api/sessions/{id}
       Response: полный PipelineState

POST   /api/sessions/{id}/approve-analogs
       Body: { approved_cte_ids: int[],
               removed_cte_ids?: int[],
               added_cte_ids?: int[] }
       Response: { current_step, all_prices[], valid_prices[],
                   outlier_prices[], outlier_justification }

POST   /api/sessions/{id}/approve-prices
       Body: { approved_price_indices: int[],
               manual_prices?: [{price, source_description}] }
       Response: { current_step, nmcc_result }

POST   /api/sessions/{id}/approve-calculation
       Body: { approved: bool }
       Response: { document_path } | redirect to step

POST   /api/sessions/{id}/go-back
       Body: { target_step: "analogs" | "prices" }
       Response: { current_step, ... }

GET    /api/sessions/{id}/document
       Response: .docx file download

GET    /api/cte/search?q=мусорные+пакеты&limit=10
       Response: список CTE из каталога (автокомплит для UI)

GET    /api/regions
       Response: ["Москва", "Пермский край", "Ямало-Ненецкий АО", ...]
```

---

## 10. СТЕК ТЕХНОЛОГИЙ

| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| Язык | Python 3.12+ | Экосистема ML/NLP |
| Менеджер зависимостей | uv (Astral) | Быстрый, детерминированный |
| Web-фреймворк | FastAPI + Pydantic V2 | Async, быстрая валидация |
| Обработка данных | Polars | Многопоточный, ~10x быстрее Pandas |
| Эмбеддинг-модель | perplexity-ai/pplx-embed-v1-0.6b | Открытая, локальная |
| Векторная БД | Qdrant (Docker) | Offline, быстрый ANN search |
| Workflow | LangGraph | Human-in-the-loop state machine |
| Генерация документа | docxtpl + Jinja2 | Шаблон .docx |
| Контейнеризация | Docker Compose | Offline deployment |

---

## 11. СТРУКТУРА ПРОЕКТА

```
src/
├── main.py                    # FastAPI app + lifespan (загрузка данных)
├── config.py                  # Settings (Pydantic BaseSettings)
├── api/
│   ├── router.py              # Все эндпоинты из §9
│   └── schemas.py             # Request/Response Pydantic модели
├── data_access/
│   ├── polars_repo.py         # ContractRepository (§6)
│   ├── qdrant_repo.py         # QdrantRepository (§3.4, §4.4)
│   └── cte_repo.py            # CTE каталог в памяти (§2.1)
├── pipeline/
│   ├── state.py               # PipelineState, AnalogItem, etc (§8.1)
│   ├── graph.py               # LangGraph StateGraph (§8.2)
│   └── nodes/
│       ├── search_analogs.py  # Этапы 1-4 (§4)
│       ├── fetch_prices.py    # Сбор цен + регион каскад (§5-6)
│       ├── filter_outliers.py # IQR + kd (§6.2-6.3)
│       ├── calculate_nmcc.py  # Приказ 567 формулы (§7)
│       └── generate_doc.py    # docxtpl rendering
├── ml/
│   ├── embeddings.py          # SentenceTransformer + build_embedding_text (§3)
│   └── matching.py            # match_score + re-ranking (§4.3, §4.6)
├── cleaning/
│   ├── clean_cte.py           # Очистка CTE каталога (§2.1)
│   └── clean_contracts.py     # Очистка контрактов (§2.2)
└── document/
    └── template.docx          # Шаблон обоснования НМЦК

data/
├── cte.json
└── contracts.json             # переименовать из "contracts (2).json"

docker-compose.yml
Dockerfile
pyproject.toml
```

---

## 12. DOCKER

### Dockerfile

```dockerfile
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
```

### docker-compose.yml

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - EMBEDDING_MODEL=perplexity-ai/pplx-embed-v1-0.6b
      - TRANSFORMERS_OFFLINE=1
    volumes:
      - ./data:/app/data
      - ./templates:/app/templates
      - ./output:/app/output
    depends_on:
      qdrant:
        condition: service_started

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_storage:/qdrant/storage

volumes:
  qdrant_storage:
```

---

## 13. ПОРЯДОК РЕАЛИЗАЦИИ

```
Phase 1: Данные
  ├── pyproject.toml + uv init
  ├── Переименовать "contracts (2).json" → "contracts.json"
  ├── src/cleaning/clean_cte.py — очистка CTE (§2.1)
  ├── src/cleaning/clean_contracts.py — очистка контрактов (§2.2)
  └── Тесты: проверить что данные чистые

Phase 2: Инфраструктура
  ├── Docker + docker-compose (Qdrant)
  ├── FastAPI skeleton + lifespan
  ├── Polars загрузка контрактов (ContractRepository)
  ├── Qdrant: загрузка CTE эмбеддингов (build_embedding_text → pplx-embed → upsert)
  └── API: GET /api/cte/search, GET /api/regions

Phase 3: Поиск аналогов
  ├── Этап 1: exact match (Polars)
  ├── Этап 2: category + match_score (§4.3)
  ├── Этап 3: Qdrant semantic search
  ├── Re-ranking (§4.6)
  └── API: POST /api/sessions → found_analogs

Phase 4: Ценовой пайплайн
  ├── fetch_prices (Polars, по approved CTE IDs)
  ├── Каскад регионов (§5.2)
  ├── Пересчёт давности kd (§6.2)
  ├── IQR outlier detection (§6.3)
  └── API: POST approve-analogs → prices

Phase 5: Расчёт НМЦК
  ├── Формулы по Приказу 567 (§7)
  ├── Проверка CV, warnings
  ├── Ручной ввод цены
  └── API: POST approve-prices → nmcc_result

Phase 6: Документ
  ├── Шаблон template.docx
  ├── docxtpl rendering
  └── API: GET /document

Phase 7: LangGraph
  ├── StateGraph + MemorySaver
  ├── interrupt nodes (wait_*)
  ├── Обратные переходы (go-back)
  └── Интеграция всех nodes
```
