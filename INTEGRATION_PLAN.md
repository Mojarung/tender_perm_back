# План интеграции Backend + Frontend: Портал поставщиков — НМЦК

## Оглавление

1. [Текущее состояние проектов](#1-текущее-состояние-проектов)
2. [Целевая архитектура](#2-целевая-архитектура)
3. [Фаза 1 — API-слой фронтенда](#3-фаза-1--api-слой-фронтенда)
4. [Фаза 2 — Подключение поиска и регионов](#4-фаза-2--подключение-поиска-и-регионов)
5. [Фаза 3 — HITL-компоненты](#5-фаза-3--hitl-компоненты)
6. [Фаза 4 — Переработка PipelineView](#6-фаза-4--переработка-pipelineview)
7. [Фаза 5 — Несколько товаров в закупке](#7-фаза-5--несколько-товаров-в-закупке)
8. [Фаза 6 — Семантический поиск и эмбеддинги](#8-фаза-6--семантический-поиск-и-эмбеддинги)
9. [Фаза 7 — Полировка и обработка ошибок](#9-фаза-7--полировка-и-обработка-ошибок)
10. [Карта изменяемых файлов](#10-карта-изменяемых-файлов)

---

## 1. Текущее состояние проектов

### 1.1 Бэкенд (FastAPI) — что есть

| Компонент | Состояние | Детали |
|-----------|-----------|--------|
| `POST /api/sessions` | Работает | Создаёт сессию, ищет аналоги через 4-стадийный каскад |
| `POST /api/sessions/{id}/approve-analogs` | Работает | Принимает список cte_id, собирает цены, фильтрует выбросы |
| `POST /api/sessions/{id}/approve-prices` | Работает | Принимает индексы цен + ручные цены, считает НМЦК |
| `POST /api/sessions/{id}/approve-calculation` | Работает | Генерирует .docx или возвращает к ценам |
| `POST /api/sessions/{id}/go-back` | Работает | Навигация назад по шагам |
| `GET /api/sessions/{id}` | Работает | Полное состояние сессии |
| `GET /api/sessions/{id}/document` | Работает | Скачивание .docx файла |
| `GET /api/cte/search?q=...&limit=10` | Работает | Текстовый поиск по названию СТЕ |
| `GET /api/cte/semantic-search?q=...&limit=10` | Работает | Поиск через эмбеддинги (Qdrant + Nvidia Nemotron) |
| `GET /api/regions` | Работает | Список уникальных регионов из контрактов |
| 4-стадийный поиск аналогов | Работает | exact → category → semantic (Qdrant) → extended |
| Сбор цен с каскадами | Работает | регион/ед.изм. каскады, kd-коэффициент |
| IQR-фильтрация выбросов | Работает | Мягкий/жёсткий IQR |
| Расчёт НМЦК по приказу №567 | Работает | mean, σ, CV%, НМЦК = mean × qty |
| Генерация .docx | Работает | docxtpl шаблон |
| Сессии в памяти | Работает | dict[str, PipelineState], теряются при рестарте |

**Ограничение бэкенда**: одна сессия = один товар. Нет понятия "закупка" из нескольких товаров.

### 1.2 Фронтенд (React + TypeScript) — что есть

| Компонент | Состояние | Детали |
|-----------|-----------|--------|
| `App.tsx` (Hero) | Готов | Лендинг с CTA "Провести закупку" |
| `Header.tsx` | Готов | Навигация, логотип |
| `CreatePurchasePage.tsx` | Частично | Выбор региона + поиск товаров, но **всё на моках** |
| `PipelineView.tsx` | Частично | ReactFlow-визуализация, но **статические данные**, нет HITL |
| `mockData.ts` | Есть | 8 товаров, 8 контрактов, 89 регионов, мок-функции |
| API-слой | **Отсутствует** | Нет ни одного реального HTTP-запроса к бэкенду |
| HITL: одобрение аналогов | **Отсутствует** | Нет UI для просмотра и выбора аналогов |
| HITL: одобрение цен | **Отсутствует** | Нет UI для просмотра цен, добавления ручных цен |
| HITL: результат НМЦК | **Отсутствует** | Нет UI для показа результата расчёта |
| Скачивание документа | **Отсутствует** | Нет кнопки скачивания .docx |
| Поля quantity/unit | **Отсутствует** | Пользователь не может указать количество и единицу |

### 1.3 Ключевые разрывы между бэкендом и фронтендом

```
ФРОНТЕНД                              БЭКЕНД
─────────                              ──────
searchCTE() → мок 600мс               GET /api/cte/search ← реальный поиск 244K товаров
russianRegions → хардкод 89шт         GET /api/regions ← реальные регионы из контрактов
Нет API-вызовов                        7 рабочих эндпоинтов ждут запросов
Нет quantity/unit полей                POST /api/sessions ожидает quantity + unit
Нет HITL-компонентов                   3 шага требуют одобрения пользователя
PipelineView — статика                 Каждая сессия проходит пошаговый pipeline
Много товаров → URL params             Одна сессия = один товар
```

---

## 2. Целевая архитектура

### 2.1 Пользовательский сценарий (целевой)

```
1. Пользователь заходит на /home → видит лендинг → жмёт "Провести закупку"

2. Страница создания закупки (/create):
   ├── Выбирает регион из списка (данные с бэкенда)
   ├── Для каждого товара:
   │   ├── Вводит поисковый запрос
   │   ├── [Опционально] включает "Умный поиск" (семантический)
   │   ├── Видит результаты поиска (реальные данные из 244K каталога)
   │   ├── Выбирает нужную СТЕ (или вводит текст вручную)
   │   ├── Указывает количество (например: 100)
   │   └── Указывает единицу измерения (например: упак)
   ├── Может добавить ещё товар (кнопка "+")
   └── Жмёт "Рассчитать НМЦК"

3. Страница пайплайна (/pipeline):
   ├── Слева: ReactFlow-граф с узлами по каждому товару
   ├── Справа: рабочая панель с текущим HITL-шагом
   │
   ├── Для каждого товара (независимо):
   │   │
   │   ├── Шаг 1: ОДОБРЕНИЕ АНАЛОГОВ
   │   │   ├── Бэкенд нашёл top-20 аналогов через 4-стадийный каскад
   │   │   ├── Пользователь видит таблицу аналогов со скорами
   │   │   ├── Выбирает нужные (чекбоксы)
   │   │   └── Жмёт "Подтвердить"
   │   │
   │   ├── Шаг 2: ОДОБРЕНИЕ ЦЕН
   │   │   ├── Бэкенд собрал цены из контрактов + отфильтровал выбросы
   │   │   ├── Пользователь видит таблицу цен (валидные + выбросы)
   │   │   ├── Может включить/выключить отдельные цены
   │   │   ├── Может добавить цену вручную
   │   │   └── Жмёт "Подтвердить"
   │   │
   │   ├── Шаг 3: РЕЗУЛЬТАТ НМЦК
   │   │   ├── Средняя цена, σ, CV%, итоговая НМЦК
   │   │   ├── Интерпретация однородности
   │   │   ├── Кнопка "Утвердить" → генерация .docx
   │   │   └── Кнопка "Вернуться к ценам"
   │   │
   │   └── Шаг 4: СКАЧИВАНИЕ ДОКУМЕНТА
   │       ├── Кнопка "Скачать .docx"
   │       └── Краткая сводка
   │
   └── Когда все товары в статусе "done":
       └── Сводная таблица: все товары, их НМЦК, итого
```

### 2.2 Схема взаимодействия frontend ↔ backend

```
CreatePurchasePage                        Backend API
──────────────────                        ───────────
При маунте:
  GET /api/regions ─────────────────────→ Список регионов
                                          ← ["Москва", "Пермский край", ...]

Поиск товара:
  GET /api/cte/search?q=пакеты ─────────→ Текстовый поиск по 244K каталогу
                                          ← [{cte_id, name, category, manufacturer, characteristics}, ...]

  GET /api/cte/semantic-search?q=... ───→ Эмбеддинг-поиск через Qdrant
                                          ← [{cte_id, name, category, manufacturer, characteristics}, ...]

Создание закупки:
  POST /api/purchases ──────────────────→ Создание N сессий
  {                                       ← {purchase_id, items: [{session_id, found_analogs}, ...]}
    region: "Пермский край",
    items: [
      {target_cte_name: "Пакеты 35л", target_cte_id: 34863000, quantity: 100, unit: "упак"},
      {target_cte_name: "Бумага А4", target_cte_id: 41200010, quantity: 500, unit: "пач"}
    ]
  }


PipelineView                              Backend API
────────────                              ───────────
Загрузка состояния:
  GET /api/purchases/{id} ──────────────→ Состояние всех сессий в закупке
                                          ← {purchase_id, items: [{session_id, current_step, ...}, ...]}

Одобрение аналогов (для каждого товара):
  POST /api/sessions/{id}/approve-analogs → Сбор цен + фильтрация
  {approved_cte_ids: [34863000, ...]}     ← {all_prices, valid_prices, outlier_prices, ...}

Одобрение цен:
  POST /api/sessions/{id}/approve-prices ─→ Расчёт НМЦК
  {approved_price_indices: [0,1,2],        ← {nmcc_result: {mean_price, sigma, cv_percent, nmcc, ...}}
   manual_prices: [{price: 90, source: "КП от поставщика"}]}

Утверждение расчёта:
  POST /api/sessions/{id}/approve-calculation → Генерация .docx
  {approved: true}                             ← {document_path: "..."}

Скачивание документа:
  GET /api/sessions/{id}/document ──────→ Файл .docx
                                          ← binary (application/vnd.openxmlformats...)

Навигация назад:
  POST /api/sessions/{id}/go-back ──────→ Возврат к предыдущему шагу
  {target_step: "analogs"}                ← {current_step: "wait_analog_approval"}
```

---

## 3. Фаза 1 — API-слой фронтенда

### 3.1 Что делаем

Создаём модуль `src/api/` с HTTP-клиентом, типами и сервисными функциями. Это фундамент для всей интеграции.

### 3.2 Новый файл: `src/api/client.ts`

Базовый HTTP-клиент с обработкой ошибок.

```typescript
// src/api/client.ts

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown
  ) {
    super(`API Error ${status}: ${statusText}`);
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    throw new ApiError(response.status, response.statusText, body);
  }
  return response.json() as Promise<T>;
}

export async function apiGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, BASE_URL);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, value);
      }
    });
  }
  const response = await fetch(url.toString());
  return handleResponse<T>(response);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(new URL(path, BASE_URL).toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(response);
}

export async function apiGetBlob(path: string): Promise<Blob> {
  const response = await fetch(new URL(path, BASE_URL).toString());
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText, null);
  }
  return response.blob();
}

export { ApiError };
```

### 3.3 Новый файл: `src/api/types.ts`

Все TypeScript-типы, отражающие Pydantic-схемы бэкенда.

```typescript
// src/api/types.ts

// ─── Аналоги (из pipeline/state.py: AnalogItem) ───

export interface AnalogItem {
  cte_id: number;
  name: string;
  category: string;
  cosine_score: number;       // 0.0–1.0, близость по эмбеддингам
  char_match_score: number;   // 0.0–1.0, совпадение характеристик
  combined_score: number;     // 0.0–1.0, итоговый скор
  source: 'exact' | 'category' | 'semantic' | 'extended' | 'manual';
  match_details: Record<string, {
    target_value: string;
    candidate_value: string;
    score: number;
    weight: number;
  }>;
}

// ─── Цены (из pipeline/state.py: PriceRecord) ───

export interface PriceRecord {
  cte_id: number;
  cte_name: string;
  price_original: number;     // Исходная цена из контракта
  price_adjusted: number;     // Цена после kd-корректировки
  kd: number;                 // Коэффициент временной корректировки
  date: string;               // Дата контракта (YYYY-MM-DD)
  region: string;             // Регион заказчика
  contract_id: number;        // ID контракта
  vat_rate: string;           // Ставка НДС
  quantity: number;           // Количество в контракте
  unit: string;               // Единица измерения
  is_outlier: boolean;        // Отмечен как выброс?
  is_regional: boolean;       // Из целевого региона?
  source: string;             // "contract" | "manual"
}

// ─── Результат НМЦК (из pipeline/state.py: NMCCResult) ───

export interface NMCCResult {
  mean_price: number;         // Средняя цена ⟨Ц⟩
  sigma: number;              // Стандартное отклонение σ
  cv_percent: number;         // Коэффициент вариации V%
  is_homogeneous: boolean;    // V ≤ 33%?
  nmcc: number;               // НМЦК = mean_price × quantity
  prices_used: number;        // Кол-во цен в расчёте
  quantity: number;           // Количество товара
  interpretation: string;     // Текстовая интерпретация
}

// ─── Поиск СТЕ ───

export interface CTESearchResult {
  cte_id: number;
  name: string;
  category: string;
  manufacturer: string;
  characteristics: Record<string, string>;  // Характеристики товара
}

// ─── Запросы ───

export interface CreateSessionRequest {
  target_cte_name: string;
  target_cte_id?: number | null;
  target_quantity: number;
  target_unit: string;
  target_region?: string | null;
}

export interface ApproveAnalogsRequest {
  approved_cte_ids: number[];
}

export interface ManualPrice {
  price: number;
  source_description: string;
}

export interface ApprovePricesRequest {
  approved_price_indices: number[];
  manual_prices?: ManualPrice[];
}

export interface ApproveCalculationRequest {
  approved: boolean;
}

export interface GoBackRequest {
  target_step: 'analogs' | 'prices';
}

// ─── Ответы ───

export interface CreateSessionResponse {
  session_id: string;
  current_step: string;
  found_analogs: AnalogItem[];
}

export interface ApproveAnalogsResponse {
  current_step: string;
  all_prices: PriceRecord[];
  valid_prices: PriceRecord[];
  outlier_prices: PriceRecord[];
  outlier_justification: string;
  region_fallback_used: boolean;
}

export interface ApprovePricesResponse {
  current_step: string;
  nmcc_result: NMCCResult;
}

export interface ApproveCalculationResponse {
  current_step: string;
  document_path: string | null;
}

export interface SessionResponse {
  session_id: string;
  current_step: string;
  target_cte_name: string;
  target_cte_id: number | null;
  target_quantity: number;
  target_unit: string;
  target_region: string | null;
  found_analogs: AnalogItem[];
  approved_analog_ids: number[];
  all_prices: PriceRecord[];
  valid_prices: PriceRecord[];
  outlier_prices: PriceRecord[];
  nmcc_result: NMCCResult | null;
  document_path: string | null;
  region_fallback_used: boolean;
  outlier_justification: string;
}

// ─── Закупка (новый эндпоинт, Фаза 5) ───

export interface PurchaseItemRequest {
  target_cte_name: string;
  target_cte_id?: number | null;
  target_quantity: number;
  target_unit: string;
}

export interface CreatePurchaseRequest {
  region?: string | null;
  items: PurchaseItemRequest[];
}

export interface CreatePurchaseResponse {
  purchase_id: string;
  items: CreateSessionResponse[];
}

export interface PurchaseStatusResponse {
  purchase_id: string;
  region: string | null;
  items: SessionResponse[];
}
```

### 3.4 Новый файл: `src/api/sessions.ts`

Функции-обёртки над HTTP-вызовами.

```typescript
// src/api/sessions.ts

import { apiGet, apiPost, apiGetBlob } from './client';
import type {
  CreateSessionRequest, CreateSessionResponse,
  ApproveAnalogsRequest, ApproveAnalogsResponse,
  ApprovePricesRequest, ApprovePricesResponse,
  ApproveCalculationRequest, ApproveCalculationResponse,
  GoBackRequest, SessionResponse,
  CTESearchResult,
  CreatePurchaseRequest, CreatePurchaseResponse, PurchaseStatusResponse,
} from './types';

// ─── Сессии ───

export function createSession(data: CreateSessionRequest) {
  return apiPost<CreateSessionResponse>('/api/sessions', data);
}

export function getSession(sessionId: string) {
  return apiGet<SessionResponse>(`/api/sessions/${sessionId}`);
}

export function approveAnalogs(sessionId: string, data: ApproveAnalogsRequest) {
  return apiPost<ApproveAnalogsResponse>(`/api/sessions/${sessionId}/approve-analogs`, data);
}

export function approvePrices(sessionId: string, data: ApprovePricesRequest) {
  return apiPost<ApprovePricesResponse>(`/api/sessions/${sessionId}/approve-prices`, data);
}

export function approveCalculation(sessionId: string, data: ApproveCalculationRequest) {
  return apiPost<ApproveCalculationResponse>(`/api/sessions/${sessionId}/approve-calculation`, data);
}

export function goBack(sessionId: string, data: GoBackRequest) {
  return apiPost<SessionResponse>(`/api/sessions/${sessionId}/go-back`, data);
}

export function downloadDocument(sessionId: string) {
  return apiGetBlob(`/api/sessions/${sessionId}/document`);
}

// ─── Поиск СТЕ ───

export function searchCTE(query: string, limit = 10) {
  return apiGet<CTESearchResult[]>('/api/cte/search', { q: query, limit: String(limit) });
}

export function semanticSearchCTE(query: string, limit = 10) {
  return apiGet<CTESearchResult[]>('/api/cte/semantic-search', { q: query, limit: String(limit) });
}

// ─── Регионы ───

export function getRegions() {
  return apiGet<string[]>('/api/regions');
}

// ─── Закупки (Фаза 5) ───

export function createPurchase(data: CreatePurchaseRequest) {
  return apiPost<CreatePurchaseResponse>('/api/purchases', data);
}

export function getPurchase(purchaseId: string) {
  return apiGet<PurchaseStatusResponse>(`/api/purchases/${purchaseId}`);
}
```

### 3.5 Конфигурация Vite

Добавить в `.env` файл фронтенда:

```env
VITE_API_URL=http://localhost:8000
```

---

## 4. Фаза 2 — Подключение поиска и регионов

### 4.1 Что делаем

Заменяем мок-функции в `CreatePurchasePage.tsx` на реальные API-вызовы. Добавляем поля количества и единицы измерения.

### 4.2 Изменения в `CreatePurchasePage.tsx`

#### 4.2.1 Загрузка регионов с бэкенда

**Было:**
```typescript
import { russianRegions, searchCTE } from './mockData';
// russianRegions — массив из 89 объектов {code, name}
```

**Стало:**
```typescript
import { getRegions, searchCTE as apiSearchCTE } from './api/sessions';

// В компоненте:
const [regions, setRegions] = useState<string[]>([]);

useEffect(() => {
  getRegions().then(setRegions).catch(console.error);
}, []);
```

**Изменение RegionSelector**: вместо `Region[]` с `code + name` — принимает `string[]` (бэкенд возвращает строки типа `"Москва"`, `"Пермский край"`).

```typescript
// Было: RegionSelector фильтрует по code и name
// Стало: RegionSelector фильтрует по строке

function RegionSelector({ regions, value, onChange }: {
  regions: string[];
  value: string;
  onChange: (region: string) => void;
}) {
  const [query, setQuery] = useState('');
  const filtered = regions.filter(r =>
    r.toLowerCase().includes(query.toLowerCase())
  );
  // ... рендер dropdown
}
```

#### 4.2.2 Замена поиска СТЕ

**Было:**
```typescript
const results = await searchCTE(query); // mockData.ts, 600мс задержка, 8 элементов
```

**Стало:**
```typescript
const results = await apiSearchCTE(query, 20); // GET /api/cte/search?q=...&limit=20
```

**Важно**: тип ответа меняется с `CTEItem` (mockData) на `CTESearchResult` (api/types).

Маппинг полей:
```
mockData.CTEItem                    →  api.CTESearchResult
───────────────                        ───────────────────
"Идентификатор СТЕ": number        →  cte_id: number
"Наименование СТЕ": string         →  name: string
"Категория": string                →  category: string
"Производитель": string            →  manufacturer: string
"характеристики СТЕ": [str,str][]  →  characteristics: Record<string, string>
```

Нужно обновить все места в `CreatePurchasePage.tsx`, где используются русские ключи, на английские.

#### 4.2.3 Добавление полей quantity и unit

Расширяем интерфейс `SearchRow`:

```typescript
// Было:
interface SearchRow {
  id: number;
  query: string;
  results: CTEItem[];
  selected: Set<number>;
  loading: boolean;
  searched: boolean;
}

// Стало:
interface SearchRow {
  id: number;
  query: string;
  results: CTESearchResult[];
  selected: Set<number>;
  loading: boolean;
  searched: boolean;
  quantity: number;        // НОВОЕ: количество товара (default: 1)
  unit: string;            // НОВОЕ: единица измерения (default: "шт")
}
```

В UI каждой `ItemSearchRow` добавляем два поля **под строкой поиска**:

```
┌─────────────────────────────────────────────────────┐
│ 🔍 [Поисковый запрос..................] [Искать]     │
├─────────────────────────────────────────────────────┤
│ Количество: [___100___]   Ед. изм.: [упак ▼]       │
├─────────────────────────────────────────────────────┤
│ ☐ 34863000 | Пакеты полимерные | Мусорные пакеты   │
│ ☑ 34863001 | Пакеты полимерные | Мусорные пакеты   │
└─────────────────────────────────────────────────────┘
```

Единицы измерения (dropdown):
```typescript
const UNITS = ['шт', 'упак', 'пач', 'кг', 'г', 'л', 'мл', 'м', 'м²', 'м³', 'компл', 'набор'];
```

### 4.3 Изменения на бэкенде: расширить CTESearchResult

В файле `src/api/schemas.py` добавить характеристики в ответ поиска:

```python
# Было:
class CTESearchResult(BaseModel):
    cte_id: int
    name: str
    category: str
    manufacturer: str

# Стало:
class CTESearchResult(BaseModel):
    cte_id: int
    name: str
    category: str
    manufacturer: str
    characteristics: dict[str, str] = {}  # ДОБАВИТЬ
```

В файле `src/api/router.py` при формировании результатов поиска добавить характеристики:

```python
# В эндпоинте GET /api/cte/search:
# Было:
return [CTESearchResult(
    cte_id=item["cte_id"],
    name=item["name"],
    category=item["category"],
    manufacturer=item["manufacturer"],
) for item in results]

# Стало:
return [CTESearchResult(
    cte_id=item["cte_id"],
    name=item["name"],
    category=item["category"],
    manufacturer=item["manufacturer"],
    characteristics=item.get("characteristics", {}),
) for item in results]
```

Аналогично для `GET /api/cte/semantic-search`.

---

## 5. Фаза 3 — HITL-компоненты

### 5.1 Что делаем

Создаём 4 новых React-компонента для каждого шага Human-in-the-Loop.

### 5.2 Компонент: `src/components/AnalogApproval.tsx`

**Назначение**: Показать найденные аналоги, дать пользователю выбрать.

**Входные данные** (props):
```typescript
interface AnalogApprovalProps {
  sessionId: string;
  targetName: string;            // Название искомого товара
  analogs: AnalogItem[];         // Найденные аналоги (до 20)
  onApproved: (response: ApproveAnalogsResponse) => void;  // Callback после одобрения
  onError: (error: Error) => void;
}
```

**Что показываем**:

```
┌──────────────────────────────────────────────────────────────┐
│ Найденные аналоги для: "Мусорные пакеты 35л"                │
│ Найдено: 12 аналогов                                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ☑ 1. Мусорные пакеты 35л (CTE: 34863000)                   │
│    Категория: Пакеты полимерные                              │
│    Источник: exact | Скор: 1.00 ████████████████████ 100%   │
│    Характеристики: Объём=35л ✓, Материал=ПВД ✓              │
│                                                              │
│ ☑ 2. Мешки для мусора 30л (CTE: 34863005)                   │
│    Категория: Пакеты полимерные                              │
│    Источник: semantic | Скор: 0.87 ████████████████░░ 87%   │
│    Характеристики: Объём=30л ~90%, Материал=ПВД ✓            │
│                                                              │
│ ☐ 3. Пакеты полиэтиленовые 120л (CTE: 34864001)            │
│    Категория: Пакеты полимерные                              │
│    Источник: category | Скор: 0.42 ████████░░░░░░░░ 42%     │
│    Характеристики: Объём=120л ✗ (не совпадает)              │
│                                                              │
│ ... (ещё 9 аналогов)                                        │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ Выбрано: 5 из 12                                            │
│ [Подтвердить аналоги →]                                     │
└──────────────────────────────────────────────────────────────┘
```

**Логика**:
1. По умолчанию выбраны аналоги с `combined_score >= 0.6` (но не более 10)
2. Пользователь может отмечать/снимать чекбоксы
3. Минимум 1 аналог должен быть выбран (валидация)
4. При клике "Подтвердить":
   ```typescript
   const response = await approveAnalogs(sessionId, {
     approved_cte_ids: [...selectedIds]
   });
   onApproved(response);
   ```

**Визуализация скоров**:
- `source` показывается как бейдж:
  - `exact` → зелёный "Точное совпадение"
  - `category` → синий "По категории"
  - `semantic` → фиолетовый "Семантический"
  - `extended` → серый "Расширенный"
- `combined_score` → прогресс-бар (0–100%)
- `match_details` → развёрнутый список характеристик при клике

**Сортировка**: по `combined_score` убывание (как с бэкенда).

---

### 5.3 Компонент: `src/components/PriceApproval.tsx`

**Назначение**: Показать собранные цены, выбросы, дать пользователю подтвердить/изменить.

**Входные данные** (props):
```typescript
interface PriceApprovalProps {
  sessionId: string;
  targetName: string;
  validPrices: PriceRecord[];
  outlierPrices: PriceRecord[];
  allPrices: PriceRecord[];
  outlierJustification: string;
  regionFallbackUsed: boolean;
  onApproved: (response: ApprovePricesResponse) => void;
  onError: (error: Error) => void;
}
```

**Что показываем**:

```
┌──────────────────────────────────────────────────────────────┐
│ Цены для: "Мусорные пакеты 35л"                            │
│ Найдено контрактов: 15 | Валидных: 12 | Выбросов: 3         │
│                                                              │
│ ⚠ Использованы цены из всех регионов (в Пермском крае      │
│   найдено менее 3 контрактов)                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ВАЛИДНЫЕ ЦЕНЫ                                                │
│ ┌────┬────────────────┬──────────┬──────────┬──────┬───────┐│
│ │ ☑  │ Товар          │ Цена ₽   │ Kd       │ Дата │Регион ││
│ ├────┼────────────────┼──────────┼──────────┼──────┼───────┤│
│ │ ☑  │ Пакеты 35л     │ 85.00    │ 1.00     │ 12.24│Москва ││
│ │ ☑  │ Пакеты 35л     │ 82.00    │ 1.05     │ 06.24│Пермь  ││
│ │ ☑  │ Пакеты мусор.  │ 93.50    │ 1.00     │ 11.24│МО     ││
│ │ ☐  │ Мешки 35л      │ 110.00   │ 1.05     │ 03.24│Сверд. ││
│ └────┴────────────────┴──────────┴──────────┴──────┴───────┘│
│                                                              │
│ ВЫБРОСЫ (IQR)        Обоснование: Q1=82, Q3=95, IQR=13     │
│ ┌────┬────────────────┬──────────┬──────────┬──────┬───────┐│
│ │ ☐  │ Пакеты 35л     │ 15.00    │ 1.00     │ 10.24│Москва ││
│ │ ☐  │ Пакеты 35л     │ 250.00   │ 1.05     │ 05.24│Пермь  ││
│ └────┴────────────────┴──────────┴──────────┴──────┴───────┘│
│                                                              │
│ ДОБАВИТЬ ЦЕНУ ВРУЧНУЮ                                        │
│ Цена: [_________] Источник: [КП от поставщика____] [+ Add]  │
│                                                              │
│ Добавленные вручную:                                        │
│ • 88.00 ₽ — "КП от ООО Пермпласт"                [✕ удал.] │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ Выбрано цен: 4 (мин. 3 для расчёта)                        │
│ [← Назад к аналогам]           [Подтвердить цены →]         │
└──────────────────────────────────────────────────────────────┘
```

**Логика**:
1. Валидные цены — по умолчанию все выбраны (☑)
2. Выбросы — по умолчанию не выбраны (☐), но можно включить
3. Ручные цены добавляются в отдельный список
4. Минимум 3 цены для расчёта (предупреждение, если меньше)
5. При "Подтвердить":
   ```typescript
   // Собрать индексы выбранных цен из allPrices
   const approvedIndices = allPrices
     .map((_, i) => i)
     .filter(i => selectedPriceIndices.has(i));

   const response = await approvePrices(sessionId, {
     approved_price_indices: approvedIndices,
     manual_prices: manualPricesList,
   });
   onApproved(response);
   ```

**Дополнительные детали в таблице цен** (при наведении/клике на строку):
- `contract_id` — ID контракта
- `quantity` — количество в контракте
- `vat_rate` — ставка НДС
- `is_regional` — иконка 📍 если из целевого региона
- `price_original` vs `price_adjusted` — показать разницу если kd ≠ 1.0

**Кнопка "Назад"**:
```typescript
await goBack(sessionId, { target_step: 'analogs' });
// → перезагрузить данные сессии, показать AnalogApproval
```

---

### 5.4 Компонент: `src/components/NMCCResult.tsx`

**Назначение**: Показать результат расчёта НМЦК, дать утвердить или вернуться.

**Входные данные** (props):
```typescript
interface NMCCResultProps {
  sessionId: string;
  targetName: string;
  targetQuantity: number;
  targetUnit: string;
  result: NMCCResult;
  onApproved: (response: ApproveCalculationResponse) => void;
  onGoBack: () => void;
  onError: (error: Error) => void;
}
```

**Что показываем**:

```
┌──────────────────────────────────────────────────────────────┐
│ Результат расчёта НМЦК: "Мусорные пакеты 35л"              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│        ┌─────────────────────────────────┐                  │
│        │     НМЦК: 8 575.00 ₽           │                  │
│        │     (100 упак × 85.75 ₽/упак)   │                  │
│        └─────────────────────────────────┘                  │
│                                                              │
│  ┌───────────────┬───────────────┬───────────────┐          │
│  │ Средняя цена  │ Отклонение    │ Кол-во цен    │          │
│  │ ⟨Ц⟩ = 85.75 ₽ │ σ = 4.23 ₽    │ n = 5         │          │
│  └───────────────┴───────────────┴───────────────┘          │
│                                                              │
│  Коэффициент вариации: V = 4.93%                            │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ (≤33%)       │
│                                                              │
│  🟢 Однородная выборка — расчёт корректен                   │
│     (V ≤ 10% — минимальная вариация)                        │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ [← Вернуться к ценам]    [Утвердить и сформировать .docx →] │
└──────────────────────────────────────────────────────────────┘
```

**Цветовая индикация CV%**:
```typescript
function getCVColor(cv: number): { color: string; label: string; icon: string } {
  if (cv <= 10) return { color: 'emerald', label: 'Однородная выборка', icon: '🟢' };
  if (cv <= 20) return { color: 'amber', label: 'Средняя вариация', icon: '🟡' };
  if (cv <= 33) return { color: 'orange', label: 'Значительная вариация', icon: '🟠' };
  return { color: 'red', label: 'НЕОДНОРОДНАЯ ВЫБОРКА', icon: '🔴' };
}
```

**Кнопки**:
- "Утвердить" → `approveCalculation(sessionId, { approved: true })` → DocumentDownload
- "Вернуться к ценам" → `goBack(sessionId, { target_step: 'prices' })`

---

### 5.5 Компонент: `src/components/DocumentDownload.tsx`

**Назначение**: Скачивание сгенерированного .docx.

**Входные данные** (props):
```typescript
interface DocumentDownloadProps {
  sessionId: string;
  targetName: string;
  nmccResult: NMCCResult;
}
```

**Что показываем**:

```
┌──────────────────────────────────────────────────────────────┐
│ ✓ Расчёт завершён: "Мусорные пакеты 35л"                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  НМЦК: 8 575.00 ₽ | CV: 4.93% | Цен: 5                    │
│                                                              │
│  [📥 Скачать обоснование НМЦК (.docx)]                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Логика скачивания**:
```typescript
async function handleDownload() {
  const blob = await downloadDocument(sessionId);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `nmcc_${sessionId}.docx`;
  a.click();
  URL.revokeObjectURL(url);
}
```

---

## 6. Фаза 4 — Переработка PipelineView

### 6.1 Что делаем

Превращаем PipelineView из статической визуализации в **интерактивный пошаговый процесс**.

### 6.2 Новая архитектура PipelineView

```
┌──────────────────────────────────────────────────────────────────┐
│ Pipeline: Закупка #abc123                                        │
├────────────────────────────┬─────────────────────────────────────┤
│                            │                                     │
│  ОБЗОР (ReactFlow)         │  РАБОЧАЯ ПАНЕЛЬ                     │
│                            │                                     │
│  Товар 1: Пакеты 35л      │  [Зависит от current_step товара]   │
│  ● Аналоги    ✓            │                                     │
│  ● Цены       ► (тут)     │  Если wait_analog_approval:         │
│  ○ НМЦК       ○            │    → <AnalogApproval />             │
│  ○ Документ   ○            │                                     │
│                            │  Если wait_price_approval:          │
│  Товар 2: Бумага А4       │    → <PriceApproval />              │
│  ● Аналоги    ► (тут)     │                                     │
│  ○ Цены       ○            │  Если wait_calc_approval:           │
│  ○ НМЦК       ○            │    → <NMCCResult />                │
│  ○ Документ   ○            │                                     │
│                            │  Если done:                         │
│                            │    → <DocumentDownload />           │
│                            │                                     │
├────────────────────────────┤                                     │
│ Активный товар: [1 ▼]     │                                     │
└────────────────────────────┴─────────────────────────────────────┘
```

### 6.3 Состояние PipelineView

```typescript
interface PipelineViewState {
  // Данные закупки
  purchaseId: string;
  region: string | null;
  items: SessionItemState[];

  // UI-состояние
  activeItemIndex: number;         // Какой товар сейчас активен в рабочей панели
  loading: boolean;
  error: string | null;
}

interface SessionItemState {
  sessionId: string;
  targetName: string;
  targetQuantity: number;
  targetUnit: string;
  currentStep: string;             // "wait_analog_approval" | "wait_price_approval" | ...

  // Данные с бэкенда (заполняются по мере прохождения)
  foundAnalogs: AnalogItem[];
  validPrices: PriceRecord[];
  outlierPrices: PriceRecord[];
  allPrices: PriceRecord[];
  outlierJustification: string;
  regionFallbackUsed: boolean;
  nmccResult: NMCCResult | null;
  documentPath: string | null;
}
```

### 6.4 Маппинг current_step → состояние узлов графа

```typescript
function getNodeStatuses(currentStep: string): Record<string, 'completed' | 'in-progress' | 'pending'> {
  switch (currentStep) {
    case 'wait_analog_approval':
      return {
        search_analogs: 'completed',
        wait_for_analog: 'in-progress',
        process_prices: 'pending',
        wait_for_price: 'pending',
        calculate_nmcc: 'pending',
      };
    case 'wait_price_approval':
      return {
        search_analogs: 'completed',
        wait_for_analog: 'completed',
        process_prices: 'completed',
        wait_for_price: 'in-progress',
        calculate_nmcc: 'pending',
      };
    case 'wait_calc_approval':
      return {
        search_analogs: 'completed',
        wait_for_analog: 'completed',
        process_prices: 'completed',
        wait_for_price: 'completed',
        calculate_nmcc: 'in-progress',
      };
    case 'done':
      return {
        search_analogs: 'completed',
        wait_for_analog: 'completed',
        process_prices: 'completed',
        wait_for_price: 'completed',
        calculate_nmcc: 'completed',
      };
    default:
      return {
        search_analogs: 'in-progress',
        wait_for_analog: 'pending',
        process_prices: 'pending',
        wait_for_price: 'pending',
        calculate_nmcc: 'pending',
      };
  }
}
```

### 6.5 Жизненный цикл PipelineView

```typescript
// 1. При маунте — загрузить данные
useEffect(() => {
  const purchaseId = searchParams.get('purchaseId');
  if (purchaseId) {
    // Фаза 5: закупка с несколькими товарами
    loadPurchase(purchaseId);
  }

  const sessionId = searchParams.get('sessionId');
  if (sessionId) {
    // Фаза 1: одна сессия
    loadSession(sessionId);
  }
}, []);

// 2. При одобрении аналогов
async function handleAnalogsApproved(response: ApproveAnalogsResponse) {
  // Обновить состояние текущего товара
  updateCurrentItem({
    currentStep: response.current_step,   // → "wait_price_approval"
    validPrices: response.valid_prices,
    outlierPrices: response.outlier_prices,
    allPrices: response.all_prices,
    outlierJustification: response.outlier_justification,
    regionFallbackUsed: response.region_fallback_used,
  });
  // ReactFlow обновит статусы узлов автоматически (через getNodeStatuses)
}

// 3. При одобрении цен
async function handlePricesApproved(response: ApprovePricesResponse) {
  updateCurrentItem({
    currentStep: response.current_step,   // → "wait_calc_approval"
    nmccResult: response.nmcc_result,
  });
}

// 4. При утверждении расчёта
async function handleCalculationApproved(response: ApproveCalculationResponse) {
  updateCurrentItem({
    currentStep: response.current_step,   // → "done"
    documentPath: response.document_path,
  });
}
```

### 6.6 Рендер рабочей панели

```tsx
function WorkPanel({ item, onUpdate }: { item: SessionItemState; onUpdate: () => void }) {
  switch (item.currentStep) {
    case 'wait_analog_approval':
      return (
        <AnalogApproval
          sessionId={item.sessionId}
          targetName={item.targetName}
          analogs={item.foundAnalogs}
          onApproved={(resp) => { /* обновить item */ }}
          onError={handleError}
        />
      );

    case 'wait_price_approval':
      return (
        <PriceApproval
          sessionId={item.sessionId}
          targetName={item.targetName}
          validPrices={item.validPrices}
          outlierPrices={item.outlierPrices}
          allPrices={item.allPrices}
          outlierJustification={item.outlierJustification}
          regionFallbackUsed={item.regionFallbackUsed}
          onApproved={(resp) => { /* обновить item */ }}
          onError={handleError}
        />
      );

    case 'wait_calc_approval':
      return (
        <NMCCResult
          sessionId={item.sessionId}
          targetName={item.targetName}
          targetQuantity={item.targetQuantity}
          targetUnit={item.targetUnit}
          result={item.nmccResult!}
          onApproved={(resp) => { /* обновить item */ }}
          onGoBack={() => { /* goBack → prices */ }}
          onError={handleError}
        />
      );

    case 'done':
      return (
        <DocumentDownload
          sessionId={item.sessionId}
          targetName={item.targetName}
          nmccResult={item.nmccResult!}
        />
      );

    default:
      return <div>Загрузка...</div>;
  }
}
```

---

## 7. Фаза 5 — Несколько товаров в закупке

### 7.1 Что делаем

Добавляем на бэкенд понятие "Закупка" (Purchase) — обёртку над N сессиями.

### 7.2 Изменения бэкенда

#### 7.2.1 Новые схемы: `src/api/schemas.py`

```python
class PurchaseItemRequest(BaseModel):
    """Один товар в закупке."""
    target_cte_name: str
    target_cte_id: int | None = None
    target_quantity: float = 1.0
    target_unit: str = "шт"

class CreatePurchaseRequest(BaseModel):
    """Запрос на создание закупки с N товарами."""
    region: str | None = None
    items: list[PurchaseItemRequest]  # 1 или более товаров

class CreatePurchaseResponse(BaseModel):
    """Ответ: purchase_id + массив созданных сессий."""
    purchase_id: str
    items: list[CreateSessionResponse]

class PurchaseStatusResponse(BaseModel):
    """Полное состояние закупки."""
    purchase_id: str
    region: str | None
    items: list[SessionResponse]
```

#### 7.2.2 Хранилище закупок: `src/api/router.py`

```python
# Рядом с существующим sessions: dict[str, PipelineState]
purchases: dict[str, dict] = {}
# Формат: { purchase_id: { "region": str, "session_ids": [str, ...] } }
```

#### 7.2.3 Новый эндпоинт: `POST /api/purchases`

```python
@router.post("/api/purchases", response_model=CreatePurchaseResponse)
async def create_purchase(request: CreatePurchaseRequest):
    purchase_id = str(uuid.uuid4())
    session_responses = []
    session_ids = []

    for item in request.items:
        # Создаём сессию для каждого товара (как существующий POST /api/sessions)
        session_request = CreateSessionRequest(
            target_cte_name=item.target_cte_name,
            target_cte_id=item.target_cte_id,
            target_quantity=item.target_quantity,
            target_unit=item.target_unit,
            target_region=request.region,
        )

        # Вызываем существующую логику создания сессии
        response = await create_session_internal(session_request)
        session_responses.append(response)
        session_ids.append(response.session_id)

    # Сохраняем маппинг
    purchases[purchase_id] = {
        "region": request.region,
        "session_ids": session_ids,
    }

    return CreatePurchaseResponse(
        purchase_id=purchase_id,
        items=session_responses,
    )
```

**Важно**: нужно выделить внутреннюю логику `POST /api/sessions` в отдельную функцию `create_session_internal()`, чтобы переиспользовать.

#### 7.2.4 Новый эндпоинт: `GET /api/purchases/{purchase_id}`

```python
@router.get("/api/purchases/{purchase_id}", response_model=PurchaseStatusResponse)
async def get_purchase(purchase_id: str):
    if purchase_id not in purchases:
        raise HTTPException(status_code=404, detail="Purchase not found")

    purchase = purchases[purchase_id]
    items = []
    for session_id in purchase["session_ids"]:
        if session_id in sessions:
            state = sessions[session_id]
            items.append(build_session_response(state))  # Существующая логика

    return PurchaseStatusResponse(
        purchase_id=purchase_id,
        region=purchase["region"],
        items=items,
    )
```

### 7.3 Изменения фронтенда

#### 7.3.1 CreatePurchasePage → создаёт Purchase

```typescript
// Было (Фаза 1): создаёт одну сессию
const response = await createSession({
  target_cte_name: rows[0].query,
  target_cte_id: [...rows[0].selected][0] || null,
  target_quantity: rows[0].quantity,
  target_unit: rows[0].unit,
  target_region: selectedRegion,
});
navigate(`/pipeline?sessionId=${response.session_id}`);

// Стало (Фаза 5): создаёт закупку с N товарами
const response = await createPurchase({
  region: selectedRegion,
  items: rows.map(row => ({
    target_cte_name: row.query,
    target_cte_id: row.selected.size > 0 ? [...row.selected][0] : null,
    target_quantity: row.quantity,
    target_unit: row.unit,
  })),
});
navigate(`/pipeline?purchaseId=${response.purchase_id}`);
```

#### 7.3.2 PipelineView — управление N товарами

- Левая панель (ReactFlow): показывает группы узлов для каждого товара (как сейчас, но с реальными статусами)
- Табы или список для переключения между товарами
- Правая панель показывает HITL для **активного** товара

#### 7.3.3 Новый компонент: `src/components/PurchaseSummary.tsx`

Показывается когда **все** товары в статусе `done`.

```
┌──────────────────────────────────────────────────────────────┐
│ ✓ Закупка завершена                                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  №  │ Товар          │ Кол-во │ Ср.цена │ НМЦК     │ CV%   │
│  ───┼────────────────┼────────┼─────────┼──────────┼───────│
│  1  │ Пакеты 35л     │ 100 уп │  85.75  │  8 575 ₽ │ 4.9%  │
│  2  │ Бумага А4      │ 500 пач│ 370.00  │185 000 ₽ │12.1%  │
│  ───┼────────────────┼────────┼─────────┼──────────┼───────│
│     │                │        │  ИТОГО: │193 575 ₽ │       │
│                                                              │
│  [📥 Скачать все документы]                                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Логика**:
```typescript
interface PurchaseSummaryProps {
  items: SessionItemState[];
}

function PurchaseSummary({ items }: PurchaseSummaryProps) {
  const totalNMCC = items.reduce((sum, item) =>
    sum + (item.nmccResult?.nmcc || 0), 0
  );

  async function downloadAll() {
    for (const item of items) {
      const blob = await downloadDocument(item.sessionId);
      // Скачать каждый файл
      saveAs(blob, `nmcc_${item.targetName}.docx`);
    }
  }

  return (/* таблица + кнопка */);
}
```

---

## 8. Фаза 6 — Семантический поиск и эмбеддинги

### 8.1 Что делаем

Добавляем переключатель "Умный поиск" на CreatePurchasePage для использования эмбеддинг-поиска через Qdrant.

### 8.2 Зачем это нужно

Текстовый поиск (`GET /api/cte/search`) ищет по точному вхождению подстроки в название. Это не найдёт:
- "мешки для мусора" → "пакеты полимерные" (синонимы)
- "trash bags" → "мусорные пакеты" (другой язык)
- "пак. п/э 35 литр." → "пакеты полиэтиленовые 35л" (аббревиатуры)

Семантический поиск (`GET /api/cte/semantic-search`) использует эмбеддинги Nvidia Nemotron и Qdrant для нахождения **семантически близких** товаров.

### 8.3 Изменения на фронтенде

В `ItemSearchRow` добавляем тогл:

```
┌─────────────────────────────────────────────────────────────┐
│ 🔍 [Поисковый запрос...............] [Умный поиск 🧠] [→]  │
└─────────────────────────────────────────────────────────────┘
```

```typescript
const [useSemanticSearch, setUseSemanticSearch] = useState(false);

async function handleSearch() {
  setLoading(true);
  try {
    const results = useSemanticSearch
      ? await semanticSearchCTE(query, 20)
      : await searchCTE(query, 20);
    setResults(results);
  } finally {
    setLoading(false);
  }
}
```

**UI-индикация**: если семантический поиск включён, показывать тултип: "Поиск по смыслу (эмбеддинги). Находит товары с похожим описанием, даже если слова отличаются."

### 8.4 Как это работает на бэкенде

Текущий эндпоинт `GET /api/cte/semantic-search`:

1. Принимает `q` — текстовый запрос пользователя
2. Вызывает `EmbeddingService.encode_single(q)` → вектор 1024 dim
3. Ищет в Qdrant: `QdrantRepository.search(vector, limit=10)`
4. Возвращает `CTESearchResult[]`

**Текущий код в router.py** использует `input_type="query"` для поиска (а при индексации использовал `input_type="passage"`) — это правильный паттерн asymmetric search.

### 8.5 Если эмбеддинги отключены

Бэкенд проверяет `settings.enable_embeddings`. Если `False` — `/api/cte/semantic-search` фоллбечит на текстовый поиск.

На фронтенде: если semantic search вернул ошибку (или можно добавить endpoint `/api/capabilities` чтобы проверять), скрыть тогл.

### 8.6 Возможное улучшение: смена модели эмбеддингов

Если нужно сменить модель (например, на локальную `sentence-transformers`):

1. В `src/config.py` изменить:
   ```python
   embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
   embedding_api_url: str = "http://localhost:11434/v1"  # Ollama или другой local API
   ```

2. В `src/ml/embeddings.py` — клиент уже использует OpenAI-compatible API, поэтому любой сервер с `/v1/embeddings` подойдёт.

3. Нужно переиндексировать Qdrant: `reindex_embeddings_on_startup: true` в `.env`.

---

## 9. Фаза 7 — Полировка и обработка ошибок

### 9.1 Обработка ошибок на фронтенде

#### 9.1.1 Глобальный error boundary

```typescript
// src/components/ErrorBoundary.tsx
// React Error Boundary для перехвата runtime ошибок
```

#### 9.1.2 API-ошибки в компонентах

Каждый HITL-компонент уже принимает `onError` callback. В PipelineView:

```typescript
function handleError(error: Error) {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 404:
        setError('Сессия не найдена. Возможно, сервер был перезагружен.');
        break;
      case 422:
        setError('Некорректные данные. Проверьте введённые значения.');
        break;
      case 500:
        setError('Ошибка сервера. Попробуйте позже.');
        break;
      default:
        setError(`Ошибка: ${error.message}`);
    }
  } else {
    setError('Нет связи с сервером. Проверьте подключение.');
  }
}
```

#### 9.1.3 Состояния загрузки

Каждое API-действие должно показывать loading-спиннер на кнопке:

```typescript
const [submitting, setSubmitting] = useState(false);

async function handleSubmit() {
  setSubmitting(true);
  try {
    const response = await approveAnalogs(sessionId, { approved_cte_ids: [...selected] });
    onApproved(response);
  } catch (e) {
    onError(e as Error);
  } finally {
    setSubmitting(false);
  }
}

// В JSX:
<button disabled={submitting}>
  {submitting ? 'Загрузка...' : 'Подтвердить аналоги'}
</button>
```

### 9.2 Пустые состояния

| Ситуация | Что показать |
|----------|-------------|
| Поиск СТЕ не нашёл результатов | "Ничего не найдено. Попробуйте другой запрос или включите умный поиск." |
| 0 аналогов найдено | "Аналоги не найдены. Попробуйте изменить запрос или указать CTE ID вручную." |
| 0 цен найдено | "Нет контрактов для выбранных аналогов. Добавьте цены вручную." |
| CV > 33% | Красное предупреждение, но кнопка "Утвердить" всё равно доступна |
| Нет шаблона .docx | "Шаблон документа не найден. Документ не может быть сгенерирован." |

### 9.3 Go-back функциональность

На каждом HITL-шаге (кроме первого) есть кнопка "Назад":

```
Аналоги → Цены:       кнопка "← К аналогам"   → goBack(id, {target_step: "analogs"})
Цены → НМЦК:          кнопка "← К ценам"       → goBack(id, {target_step: "prices"})
НМЦК → Цены:          кнопка "← Вернуться"     → approveCalculation(id, {approved: false})
```

При go-back перезагрузить сессию через `getSession()` для получения актуального состояния.

### 9.4 Адаптивность

- На мобильных устройствах: рабочая панель занимает весь экран (ReactFlow скрыт, доступен через кнопку)
- Таблицы цен горизонтально скроллятся
- Кнопки подтверждения фиксированы внизу экрана (sticky footer)

---

## 10. Карта изменяемых файлов

### 10.1 Бэкенд — изменяемые файлы

| Файл | Фаза | Что меняем |
|------|------|-----------|
| `src/api/schemas.py` | 2, 5 | Добавить `characteristics` в `CTESearchResult`. Добавить `PurchaseItemRequest`, `CreatePurchaseRequest`, `CreatePurchaseResponse`, `PurchaseStatusResponse` |
| `src/api/router.py` | 2, 5 | Добавить `characteristics` в ответы поиска. Добавить эндпоинты `POST /api/purchases`, `GET /api/purchases/{id}`. Выделить `create_session_internal()` |

### 10.2 Бэкенд — файлы без изменений

| Файл | Почему не меняем |
|------|-----------------|
| `src/pipeline/nodes/*` | Вся логика расчётов уже работает |
| `src/data_access/*` | Репозитории работают |
| `src/ml/*` | Эмбеддинги и матчинг работают |
| `src/config.py` | Настройки достаточны (опционально: `frontend_url`) |
| `src/main.py` | Запуск и lifespan без изменений |

### 10.3 Фронтенд — новые файлы

| Файл | Фаза | Назначение |
|------|------|-----------|
| `src/api/client.ts` | 1 | HTTP-клиент (fetch + error handling) |
| `src/api/types.ts` | 1 | TypeScript-типы бэкенда |
| `src/api/sessions.ts` | 1 | API-функции (createSession, approveAnalogs, ...) |
| `src/components/AnalogApproval.tsx` | 3 | HITL: выбор аналогов |
| `src/components/PriceApproval.tsx` | 3 | HITL: одобрение цен |
| `src/components/NMCCResult.tsx` | 3 | Результат расчёта |
| `src/components/DocumentDownload.tsx` | 3 | Скачивание .docx |
| `src/components/PurchaseSummary.tsx` | 5 | Сводка по закупке |
| `.env` | 1 | `VITE_API_URL=http://localhost:8000` |

### 10.4 Фронтенд — изменяемые файлы

| Файл | Фаза | Что меняем |
|------|------|-----------|
| `src/CreatePurchasePage.tsx` | 2, 5, 6 | API вместо моков. Поля quantity/unit. Семантический тогл. createPurchase вместо URL-params |
| `src/PipelineView.tsx` | 4, 5 | Загрузка из API. Рабочая панель с HITL-компонентами. Управление N товарами |
| `src/mockData.ts` | 2 | Удалить мок-функции `searchCTE`, `getContractsForCTEs`. Оставить типы (или перенести в api/types.ts) |

### 10.5 Фронтенд — файлы без изменений

| Файл | Почему не меняем |
|------|-----------------|
| `src/App.tsx` | Лендинг работает |
| `src/components/Header.tsx` | Навигация работает |
| `src/main.tsx` | Роутинг работает (но можно обновить маршруты) |
| `src/index.css` | Стили работают |
| Конфиги (vite, tsconfig, tailwind) | Работают |

---

## Итого

| Фаза | Объём работ | Зависимости |
|------|------------|-------------|
| **Фаза 1**: API-слой фронтенда | 3 новых файла | Нет |
| **Фаза 2**: Поиск + регионы + qty/unit | Изменение 2 файлов (front + back) | Фаза 1 |
| **Фаза 3**: HITL-компоненты | 4 новых компонента | Фаза 1 |
| **Фаза 4**: PipelineView переработка | Крупное изменение 1 файла | Фазы 1, 3 |
| **Фаза 5**: Несколько товаров | Backend: 2 файла. Frontend: 2 файла | Фаза 4 |
| **Фаза 6**: Семантический поиск | Мелкое изменение UI | Фаза 2 |
| **Фаза 7**: Полировка | Все файлы HITL | Все фазы |
