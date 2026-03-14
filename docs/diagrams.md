# Диаграммы

## UI User Story — путь пользователя

```mermaid
flowchart TD
    START(("Начало")) --> FORM

    FORM["<b>Экран 1: Ввод товара</b><br/>─────────────────<br/>Поле поиска с автокомплитом<br/>Количество, единица, регион<br/><br/>Кнопка: <b>Найти аналоги</b>"]
    FORM -->|"POST /api/sessions"| ANALOGS

    ANALOGS["<b>Экран 2: Аналоги</b><br/>─────────────────<br/>Таблица из 20 товаров<br/>Чекбоксы для выбора<br/>Колонки: название, категория,<br/>score, источник<br/><br/>Кнопки: <b>Подтвердить</b> | Назад"]
    ANALOGS -->|"POST /approve-analogs"| PRICES

    PRICES["<b>Экран 3: Цены</b><br/>─────────────────<br/>Таблица цен из контрактов<br/>Выбросы помечены красным<br/>Кнопка 'Добавить цену вручную'<br/>Инфо: регион, дата, kd<br/><br/>Кнопки: <b>Рассчитать</b> | Назад"]
    PRICES -->|"POST /approve-prices"| RESULT

    RESULT["<b>Экран 4: Результат НМЦК</b><br/>─────────────────<br/>Средняя цена: XX руб<br/>Кол-во: N шт<br/>НМЦК: XXXX руб<br/>CV: XX% (однородность)<br/><br/>Кнопки: <b>Сформировать документ</b> | Назад"]
    RESULT -->|"POST /approve-calculation"| DOC

    DOC["<b>Экран 5: Документ</b><br/>─────────────────<br/>Документ .docx готов<br/><br/>Кнопка: <b>Скачать</b>"]

    %% Возвраты
    ANALOGS -.->|"Назад"| FORM
    PRICES -.->|"go-back → analogs"| ANALOGS
    RESULT -.->|"go-back → prices"| PRICES
    RESULT -.->|"go-back → analogs"| ANALOGS

    style FORM fill:#e3f2fd,stroke:#1565c0
    style ANALOGS fill:#e8f5e9,stroke:#2e7d32
    style PRICES fill:#fff3e0,stroke:#e65100
    style RESULT fill:#f3e5f5,stroke:#6a1b9a
    style DOC fill:#e0f2f1,stroke:#00695c
    style START fill:#fff
```

## Навигация между шагами (go-back)

```mermaid
stateDiagram-v2
    [*] --> Ввод_товара

    Ввод_товара --> Аналоги : Найти аналоги
    Аналоги --> Цены : Подтвердить аналоги
    Цены --> Результат : Рассчитать НМЦК
    Результат --> Документ : Сформировать

    Цены --> Аналоги : Назад
    Результат --> Цены : Назад к ценам
    Результат --> Аналоги : Назад к аналогам

    note right of Аналоги
        При возврате сюда
        аналоги сохранены,
        можно изменить выбор
    end note

    note right of Цены
        При возврате сюда
        цены пересчитываются
        с новыми аналогами
    end note

    note right of Результат
        Если CV > 33%
        система рекомендует
        вернуться и пересмотреть
    end note
```

## Экран 2: что видит пользователь (аналоги)

```mermaid
flowchart LR
    subgraph screen["Экран: Выбор аналогов"]
        direction TB
        HEADER["<b>Ручка шариковая Berlingo Tribase 0.5мм</b><br/>Категория: Ручки канцелярские | Кол-во: 100 шт | Регион: Москва"]

        subgraph table["Найденные аналоги"]
            direction TB
            R1["☑ Ручка шариковая Berlingo Tribase черная 0.5мм<br/><i>exact | score: 1.00</i>"]
            R2["☑ Ручка шариковая Berlingo Tribase синяя 0.5мм<br/><i>category | score: 0.63 | Цвет: не совпал</i>"]
            R3["☑ Ручка канцелярская Attache шариковая синяя<br/><i>category | score: 0.60</i>"]
            R4["☐ Ручка гелевая Berlingo Velvet синяя<br/><i>category | score: 0.35 | Тип: не совпал</i>"]
        end

        BUTTONS["<b>Подтвердить выбранные (3)</b> &nbsp;&nbsp; | &nbsp;&nbsp; Назад"]
    end

    style R1 fill:#c8e6c9
    style R2 fill:#c8e6c9
    style R3 fill:#c8e6c9
    style R4 fill:#ffcdd2
```

## Экран 3: что видит пользователь (цены)

```mermaid
flowchart LR
    subgraph screen["Экран: Подтверждение цен"]
        direction TB
        INFO["13 цен найдено | Регион: Москва | Единица: шт<br/><i>Все цены из целевого региона</i>"]

        subgraph table["Цены из контрактов"]
            direction TB
            P1["☑ Berlingo Tribase черная | 10.14 руб | Москва | 04.06.2025 | kd=1.0"]
            P2["☑ Attache шариковая | 16.54 руб | Москва | 29.04.2025 | kd=1.0"]
            P3["☑ Berlingo Tribase синяя | 40.75 руб | Москва | 27.11.2025 | kd=1.0"]
            P4["☑ STAFF Basic Budget | 12.33 руб | Москва | 15.03.2025 | kd=1.0"]
        end

        subgraph iqr["Фильтрация выбросов"]
            direction TB
            IQR_INFO["Q1=12.33 | Q3=24.87 | IQR=12.54<br/>Допустимый диапазон: 0 — 43.68 руб<br/>Отсечено выбросов: 0"]
        end

        MANUAL["+ Добавить цену вручную"]
        BUTTONS2["<b>Рассчитать НМЦК</b> &nbsp;&nbsp; | &nbsp;&nbsp; Назад к аналогам"]
    end

    style P1 fill:#c8e6c9
    style P2 fill:#c8e6c9
    style P3 fill:#fff9c4
    style P4 fill:#c8e6c9
```

## Экран 4: результат НМЦК

```mermaid
flowchart LR
    subgraph screen["Экран: Результат расчёта"]
        direction TB
        TITLE["<b>РЕЗУЛЬТАТ РАСЧЁТА НМЦК</b>"]

        subgraph calc["Расчёт по Приказу 567"]
            direction TB
            C1["Средняя цена за единицу: <b>19.07 руб</b>"]
            C2["Среднеквадратичное отклонение: <b>8.74 руб</b>"]
            C3["Коэффициент вариации: <b>45.83%</b> ⚠️ > 33%"]
            C4["Использовано источников: <b>13</b>"]
        end

        subgraph nmcc[""]
            direction TB
            FORMULA["НМЦК = 19.07 × 100 = <b>1 906.77 руб</b>"]
        end

        WARNING["⚠️ НЕОДНОРОДНАЯ ВЫБОРКА<br/>Рекомендуется пересмотреть выбор аналогов или цен"]

        BUTTONS3["<b>Сформировать документ</b> | Назад к ценам | Назад к аналогам"]
    end

    style C3 fill:#fff9c4
    style WARNING fill:#ffcdd2
    style FORMULA fill:#e8f5e9
```

## Полный Sequence — включая возвраты

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant F as Frontend
    participant API as Backend API

    U->>F: Вводит "Ручка шариковая", 100 шт, Москва
    F->>API: POST /api/sessions
    API-->>F: session_id + 20 аналогов
    F-->>U: Показывает таблицу аналогов

    U->>F: Выбирает 5 аналогов, нажимает "Подтвердить"
    F->>API: POST /approve-analogs {cte_ids}
    API-->>F: 13 цен (valid + outliers)
    F-->>U: Показывает таблицу цен

    Note over U,F: Пользователь видит что цена 40.75<br/>слишком высокая, хочет убрать

    U->>F: Снимает галочку с цены 40.75, нажимает "Рассчитать"
    F->>API: POST /approve-prices {indices без 40.75}
    API-->>F: НМЦК = 1574 руб, CV = 28% ✅
    F-->>U: Показывает результат

    alt CV > 33% — неоднородно
        F-->>U: Предупреждение: пересмотрите выбор
        U->>F: Нажимает "Назад к аналогам"
        F->>API: POST /go-back {target_step: "analogs"}
        API-->>F: step = wait_analog_approval
        F-->>U: Снова экран аналогов
    else CV ≤ 33% — всё ок
        U->>F: Нажимает "Сформировать документ"
        F->>API: POST /approve-calculation {approved: true}
        API-->>F: document_path
        U->>F: Нажимает "Скачать"
        F->>API: GET /sessions/{id}/document
        API-->>F: файл .docx
    end
```
