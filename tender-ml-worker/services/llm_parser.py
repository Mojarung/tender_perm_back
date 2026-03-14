import json
import os
from llama_cpp import Llama, LlamaGrammar

MODEL_PATH = os.getenv("LLM_MODEL_PATH", "../model_weights/qwen-slm.gguf")

try:
    if not os.path.exists(MODEL_PATH):
        print(f"Warning: LLM model file not found at {MODEL_PATH}")
        llm, grammar = None, None
    else:
        llm = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=4, verbose=False)
        grammar_str = r'''root ::= "{" ws (string ws ":" ws value (ws "," ws string ws ":" ws value)*)? ws "}"
value ::= string | number | boolean | null | array | object
string ::= "\"" ([^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F]))* "\""
number ::= "-"? ("0" | [1-9] [0-9]*) ("." [0-9]+)? ([eE] [-+]? [0-9]+)?
boolean ::= "true" | "false"
null ::= "null"
array ::= "[" ws (value (ws "," ws value)*)? ws "]"
object ::= "{" ws (string ws ":" ws value (ws "," ws string ws ":" ws value)*)? ws "}"
ws ::= ([ \t\n] ws)?'''
        grammar = LlamaGrammar.from_string(grammar_str)
except Exception as e:
    print(f"Failed to load GGUF model: {e}")
    llm, grammar = None, None

def parse_text(raw_text: str) -> dict:
    """
    Invokes Qwen3-8B-Instruct-GGUF via llama-cpp-python to parse unformatted
    characteristics text into a strict JSON dictionary.
    """
    if llm is None:
        try:
            arr = json.loads(raw_text)
            if isinstance(arr, list) and all(isinstance(x, list) and len(x) == 2 for x in arr):
                return {k: v for k, v in arr}
        except Exception:
            pass
        return {"raw_extracted": raw_text}

    prompt = f"<|im_start|>system\nВы - ИИ-ассистент, строго извлекающий параметры в формате JSON.<|im_end|>\n<|im_start|>user\nИзвлеки параметры из текста: {raw_text}<|im_end|>\n<|im_start|>assistant\n```json\n"
    
    try:
        response = llm(prompt, grammar=grammar, max_tokens=512)
        return json.loads(response['choices'][0]['text'])
    except Exception as e:
        print(f"LLM generation parsing failed: {e}")
        return {"raw_extracted": raw_text}
