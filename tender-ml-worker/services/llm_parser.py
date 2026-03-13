import json

def parse_text(raw_text: str) -> dict:
    """
    Invokes Qwen3-8B-Instruct-GGUF via llama-cpp-python to parse unformatted
    characteristics text into a strict JSON dictionary.
    
    For the hackathon scope, this parses basic structures or mimics LLM response.
    """
    # Actual implementation concept:
    # llm = Llama(model_path="/app/models/qwen3-8b-instruct.Q4_K_M.gguf", n_ctx=2048)
    # grammar_str = r'''root ::= "{" ws (string ws ":" ws value (ws "," ws string ws ":" ws value)*)? ws "}"...'''
    # response = llm(f"Extract parameters as JSON from: {raw_text}", grammar=LlamaGrammar.from_string(grammar_str))
    # return json.loads(response['choices'][0]['text'])

    # Temporary functional fallback for data ingestion scripts
    try:
        arr = json.loads(raw_text)
        if isinstance(arr, list) and all(isinstance(x, list) and len(x) == 2 for x in arr):
            return {k: v for k, v in arr}
    except Exception:
        pass
    
    return {"raw_extracted": raw_text}
