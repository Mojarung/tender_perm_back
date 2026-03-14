"""Document generation service — creates .docx justification report."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)


def generate_nmck_document(
    template_path: Path,
    output_dir: Path,
    session_id: str,
    target_name: str,
    analogs: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    outliers: list[dict[str, Any]],
    calculation: dict[str, Any],
    justification: list[dict[str, Any]],
) -> str:
    """
    Generate a .docx justification document from the pipeline results.

    Returns the path to the generated file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"nmck_justification_{session_id}.docx"

    # If the template exists, use it; otherwise create a simple document
    if template_path.exists():
        doc = DocxTemplate(str(template_path))
        context = _build_template_context(
            session_id=session_id,
            target_name=target_name,
            analogs=analogs,
            prices=prices,
            outliers=outliers,
            calculation=calculation,
            justification=justification,
        )
        doc.render(context)
        doc.save(str(output_path))
    else:
        logger.warning("Template not found at %s, creating basic document", template_path)
        _create_basic_document(
            output_path=output_path,
            session_id=session_id,
            target_name=target_name,
            analogs=analogs,
            prices=prices,
            outliers=outliers,
            calculation=calculation,
            justification=justification,
        )

    logger.info("Document generated: %s", output_path)
    return str(output_path)


def _build_template_context(
    session_id: str,
    target_name: str,
    analogs: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    outliers: list[dict[str, Any]],
    calculation: dict[str, Any],
    justification: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build context dict for docxtpl template rendering."""
    return {
        "session_id": session_id,
        "date": datetime.now().strftime("%d.%m.%Y"),
        "target_name": target_name,
        "analogs": analogs,
        "analogs_count": len(analogs),
        "prices": prices,
        "prices_count": len(prices),
        "outliers": outliers,
        "outliers_count": len(outliers),
        "weighted_average": calculation.get("weighted_average_price", 0),
        "median": calculation.get("median_price", 0),
        "cv": calculation.get("coefficient_of_variation", 0),
        "is_homogeneous": calculation.get("is_homogeneous", True),
        "nmck_per_unit": calculation.get("nmck_per_unit", 0),
        "total_nmck": calculation.get("total_nmck", 0),
        "price_range_min": calculation.get("price_range_min", 0),
        "price_range_max": calculation.get("price_range_max", 0),
        "num_prices_used": calculation.get("num_prices_used", 0),
        "justification": justification,
    }


def _create_basic_document(
    output_path: Path,
    session_id: str,
    target_name: str,
    analogs: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    outliers: list[dict[str, Any]],
    calculation: dict[str, Any],
    justification: list[dict[str, Any]],
) -> None:
    """Create a basic .docx document without a template using python-docx."""
    from docx import Document
    from docx.shared import Pt

    doc = Document()

    # Title
    title = doc.add_heading("Обоснование начальной (максимальной) цены контракта", level=0)

    doc.add_paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y')}")
    doc.add_paragraph(f"Сессия: {session_id}")
    doc.add_paragraph(f"Позиция: {target_name}")

    # Analogs section
    doc.add_heading("1. Сопоставимые позиции (аналоги)", level=1)
    if analogs:
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "ID СТЕ"
        hdr[1].text = "Наименование"
        hdr[2].text = "Категория"
        hdr[3].text = "Основание выбора"
        for analog in analogs:
            row = table.add_row().cells
            row[0].text = str(analog.get("cte_id", ""))
            row[1].text = analog.get("name", "")
            row[2].text = analog.get("category", "")
            row[3].text = analog.get("match_reason", "")
    else:
        doc.add_paragraph("Аналоги не найдены.")

    # Prices section
    doc.add_heading("2. Ценовая информация", level=1)
    if prices:
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text = "Позиция СТЕ"
        hdr[1].text = "Цена за ед."
        hdr[2].text = "Регион"
        hdr[3].text = "Дата контракта"
        hdr[4].text = "ID контракта"
        for p in prices:
            row = table.add_row().cells
            row[0].text = str(p.get("Наименование позиции СТЕ", p.get("cte_name", "")))
            row[1].text = f'{p.get("Цена за единицу", p.get("price", 0)):.2f}'
            row[2].text = str(p.get("Регион заказчика", p.get("region", "")))
            row[3].text = str(p.get("Дата заключения контракта", p.get("contract_date", "")))
            row[4].text = str(p.get("Идентификатор контракта", p.get("contract_id", "")))
    else:
        doc.add_paragraph("Ценовые данные отсутствуют.")

    # Outliers section
    if outliers:
        doc.add_heading("3. Исключённые выбросы", level=1)
        doc.add_paragraph(f"Исключено {len(outliers)} позиций методом IsolationForest:")
        for o in outliers:
            price_val = o.get("Цена за единицу", o.get("price", 0))
            name_val = o.get("Наименование позиции СТЕ", o.get("cte_name", ""))
            doc.add_paragraph(f"  • {name_val}: {price_val:.2f} ₽", style="List Bullet")

    # Calculation section
    doc.add_heading("4. Расчёт НМЦК", level=1)

    calc_data = [
        ("Число использованных цен", str(calculation.get("num_prices_used", 0))),
        ("Средневзвешенная цена", f'{calculation.get("weighted_average_price", 0):.2f} ₽'),
        ("Медиана", f'{calculation.get("median_price", 0):.2f} ₽'),
        ("Коэффициент вариации", f'{calculation.get("coefficient_of_variation", 0):.1f}%'),
        ("Однородность выборки", "Да" if calculation.get("is_homogeneous", True) else "Нет"),
        ("НМЦК за единицу", f'{calculation.get("nmck_per_unit", 0):.2f} ₽'),
        ("Итого НМЦК", f'{calculation.get("total_nmck", 0):.2f} ₽'),
        (
            "Допустимый ценовой диапазон",
            f'{calculation.get("price_range_min", 0):.2f} — {calculation.get("price_range_max", 0):.2f} ₽',
        ),
    ]
    table = doc.add_table(rows=len(calc_data), cols=2)
    table.style = "Table Grid"
    for i, (label, value) in enumerate(calc_data):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = value

    # Justification section
    doc.add_heading("5. Обоснование", level=1)
    for j in justification:
        doc.add_paragraph(f"{j.get('description', '')}", style="List Bullet")
        data = j.get("data", {})
        for k, v in data.items():
            doc.add_paragraph(f"    {k}: {v}")

    doc.save(str(output_path))
