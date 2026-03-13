from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from workflows.nmcc_graph import graph_app
import uuid

router = APIRouter()

class CalculateRequest(BaseModel):
    target_ste_id: str
    target_region: str
    selected_prices: List[float]

class ResumeRequest(BaseModel):
    thread_id: str
    edited_valid_prices: List[float]

active_threads = {}

@router.post("/calculate")
async def calculate_nmck(payload: CalculateRequest):
    thread_id = str(uuid.uuid4())
    initial_state = {
        "target_ste_id": payload.target_ste_id,
        "target_region": payload.target_region,
        "selected_prices": payload.selected_prices,
        "human_approved": False
    }
    
    final_state = await graph_app.ainvoke(initial_state)
    active_threads[thread_id] = final_state
    
    return {
        "thread_id": thread_id,
        "state": final_state
    }

@router.post("/resume")
async def resume_nmck(payload: ResumeRequest):
    state = active_threads.get(payload.thread_id)
    if not state:
        return {"error": "Thread not found"}
        
    state["valid_prices"] = payload.edited_valid_prices
    state["human_approved"] = True
    state["requires_manual_input"] = False
    
    # We re-invoke to finish the graph from the math node using the new values
    final_state = await graph_app.ainvoke(state)
    active_threads[payload.thread_id] = final_state
    
    return {"state": final_state}
