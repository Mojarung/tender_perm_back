import json

def parse_text(raw_text: str) -> dict:
    """
    Invokes Qwen3-8B-Instruct-GGUF via llama-cpp-python to parse unformatted
    characteristics text into a strict JSON dictionary.
    
    For the hackathon scope, this parses basic structures or mimics LLM response.
    """
    # Temporary functional fallback for data ingestion scripts
    try:
        arr = json.loads(raw_text)
        if isinstance(arr, list) and all(isinstance(x, list) and len(x) == 2 for x in arr):
            return {k: v for k, v in arr}
    except Exception:
        pass
    
    return {"raw_extracted": raw_text}
