import json

def parse_text(raw_text: str) -> dict:
    """
    Parses strictly formatted array of characteristics into a dictionary.
    Assumes `raw_text` is a JSON string of pairs [[key, value], ...].
    If it's plain text or unstructured, falls back to returning it as `raw_extracted`.
    """
    try:
        arr = json.loads(raw_text)
        if isinstance(arr, list) and all(isinstance(x, list) and len(x) == 2 for x in arr):
            return {str(k): str(v) for k, v in arr}
    except Exception:
        pass
    
    return {"raw_extracted": raw_text}
