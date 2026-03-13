from typing import TypedDict, List
from langgraph.graph import StateGraph, END
import httpx
import os
import polars as pl

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://tender_ml_worker:8001")

class NMCCState(TypedDict, total=False):
    target_ste_id: str
    target_region: str
    selected_prices: List[float]
    valid_prices: List[float]
    outliers: List[float]
    nmck_value: float
    variation_coefficient: float
    requires_manual_input: bool
    human_approved: bool
    ai_explanation: str

async def detect_outliers_node(state: NMCCState) -> NMCCState:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{ML_SERVICE_URL}/internal/ml/detect-outliers",
                json={"prices": state["selected_prices"]}
            )
            data = response.json()
            state["valid_prices"] = data.get("valid_prices", [])
            state["outliers"] = data.get("outliers", [])
        except httpx.RequestError:
            # Fallback if ML worker is not available during dev
            state["valid_prices"] = state["selected_prices"]
            state["outliers"] = []
    
    # If there are outliers, we require human input before proceeding
    if state["outliers"] and not state.get("human_approved", False):
        state["requires_manual_input"] = True
    else:
        state["requires_manual_input"] = False
        
    return state

def human_in_loop_node(state: NMCCState) -> NMCCState:
    # State is returned to UI. User edits `valid_prices`.
    # Handled via API Resume.
    return state

def calculate_math_node(state: NMCCState) -> NMCCState:
    prices = state.get("valid_prices", [])
    if not prices:
        state["nmck_value"] = 0.0
        state["variation_coefficient"] = 0.0
        return state
        
    df = pl.DataFrame({"price": prices})
    mean_price = df["price"].mean()
    std_price = df["price"].std() if len(prices) > 1 else 0.0
    
    cv = (std_price / mean_price) * 100 if mean_price and mean_price > 0 else 0.0
    
    state["nmck_value"] = float(mean_price)
    state["variation_coefficient"] = float(cv)
    return state
    
def explainable_ai_node(state: NMCCState) -> NMCCState:
    outlier_len = len(state.get("outliers", []))
    if outlier_len > 0:
        state["ai_explanation"] = f"Модель ИИ выявила и исключила {outlier_len} аномальных цен из выборки. Оставшиеся {len(state.get('valid_prices', []))} цен использованы для расчета."
    else:
        state["ai_explanation"] = f"Расчет произведен на основе {len(state.get('valid_prices', []))} подтвержденных цен (выбросов не найдено)."
    return state

# Graph Setup
def should_interrupt(state: NMCCState) -> str:
    if state.get("requires_manual_input") and not state.get("human_approved"):
        return "human"
    return "math"

workflow = StateGraph(NMCCState)
workflow.add_node("detect", detect_outliers_node)
workflow.add_node("human", human_in_loop_node)
workflow.add_node("math", calculate_math_node)
workflow.add_node("explain", explainable_ai_node)

workflow.set_entry_point("detect")
workflow.add_conditional_edges("detect", should_interrupt, {
    "human": "human",
    "math": "math"
})
workflow.add_edge("human", "math")
workflow.add_edge("math", "explain")
workflow.add_edge("explain", END)

graph_app = workflow.compile()
