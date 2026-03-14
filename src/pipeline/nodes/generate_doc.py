from pathlib import Path
from docxtpl import DocxTemplate
from src.pipeline.state import PipelineState


def generate_document(state: PipelineState, template_path: Path, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"nmcc_{state.session_id}.docx"

    tpl = DocxTemplate(str(template_path))

    prices_data = []
    for i, p in enumerate(state.user_approved_prices, 1):
        prices_data.append({
            "num": i,
            "cte_name": p.cte_name,
            "price_original": f"{p.price_original:.2f}",
            "price_adjusted": f"{p.price_adjusted:.2f}",
            "kd": f"{p.kd:.2f}",
            "date": p.date,
            "region": p.region,
            "contract_id": p.contract_id,
        })

    nmcc = state.nmcc_result
    context = {
        "session_id": state.session_id,
        "target_name": state.target_cte_name,
        "target_quantity": state.target_quantity,
        "target_unit": state.target_unit,
        "target_region": state.target_region or "Все регионы",
        "prices": prices_data,
        "mean_price": f"{nmcc.mean_price:.2f}" if nmcc else "—",
        "sigma": f"{nmcc.sigma:.2f}" if nmcc else "—",
        "cv_percent": f"{nmcc.cv_percent:.2f}" if nmcc else "—",
        "is_homogeneous": nmcc.is_homogeneous if nmcc else False,
        "nmcc": f"{nmcc.nmcc:.2f}" if nmcc else "—",
        "prices_used": nmcc.prices_used if nmcc else 0,
        "interpretation": nmcc.interpretation if nmcc else "—",
        "outlier_justification": state.outlier_justification,
        "region_fallback": state.region_fallback_used,
    }

    tpl.render(context)
    tpl.save(str(output_path))
    return str(output_path)
