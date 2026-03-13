"""SLM parsing service using Qwen2.5-0.5B-Instruct via llama-cpp-python.

Model: Qwen/Qwen2.5-0.5B-Instruct-GGUF (Q4_K_M)
Runtime: llama-cpp-python
Constraint: JSON Schema grammar enforcement to prevent hallucinations.
"""

import json
import logging

from llama_cpp import Llama

from config import SLM_MODEL_PATH, SLM_CONTEXT_SIZE, SLM_MAX_TOKENS

logger = logging.getLogger(__name__)

# JSON grammar to force structured output
JSON_GRAMMAR = r"""
root   ::= "{" ws members ws "}"
members ::= pair ("," ws pair)*
pair   ::= ws string ws ":" ws value
string ::= "\"" chars "\""
chars  ::= char*
char   ::= [^"\\] | "\\" escape
escape ::= ["\\nrt/]
value  ::= string | number | "null"
number ::= "-"? [0-9]+ ("." [0-9]+)?
ws     ::= [ \t\n]*
"""

PARSE_PROMPT_TEMPLATE = """Ты — конвертер данных. Преобразуй массив характеристик в плоский JSON-объект.

Правила:
- Ключ = название характеристики (без единиц измерения)
- Значение = число (float) если возможно, иначе строка
- Стандартизируй единицы: "мкм" → убрать, "мм" → убрать, просто число

Входные данные:
{raw_text}

Выведи ТОЛЬКО JSON-объект, без пояснений:"""


class SLMService:
    """Parses raw STE characteristics into structured JSON using a local SLM."""

    def __init__(self) -> None:
        self._model: Llama | None = None
        self._loaded = False

    def load(self) -> None:
        """Load the GGUF model."""
        if not SLM_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"SLM model not found at {SLM_MODEL_PATH}. "
                f"Download Qwen2.5-0.5B-Instruct-GGUF (Q4_K_M) first."
            )

        logger.info(f"Loading SLM from {SLM_MODEL_PATH}...")
        self._model = Llama(
            model_path=str(SLM_MODEL_PATH),
            n_ctx=SLM_CONTEXT_SIZE,
            n_threads=4,
            n_gpu_layers=0,  # CPU only
            verbose=False,
        )
        self._loaded = True
        logger.info("SLM model loaded successfully")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def parse_characteristics(self, raw_text: str) -> dict:
        """
        Parse raw characteristics array text into a flat JSON object.

        Example input:  '[["Количество в упаковке", "30.00000"], ["Толщина, мкм", "50.00000"]]'
        Example output: {"Количество в упаковке": 30.0, "Толщина": 50.0}
        """
        if not self._loaded:
            raise RuntimeError("SLM not loaded. Call load() first.")

        # Try simple parsing first (for well-structured arrays)
        try:
            parsed = self._parse_simple(raw_text)
            if parsed:
                return parsed
        except Exception:
            pass

        # Fall back to SLM
        prompt = PARSE_PROMPT_TEMPLATE.format(raw_text=raw_text)

        response = self._model.create_completion(
            prompt,
            max_tokens=SLM_MAX_TOKENS,
            temperature=0.1,
            top_p=0.9,
            grammar=self._get_grammar(),
            stop=["\n\n"],
        )

        output_text = response["choices"][0]["text"].strip()

        try:
            return json.loads(output_text)
        except json.JSONDecodeError:
            logger.warning(f"SLM returned invalid JSON: {output_text[:200]}")
            # Final fallback: simple parsing
            return self._parse_simple(raw_text) or {}

    def _parse_simple(self, raw_text: str) -> dict | None:
        """
        Try to parse the raw characteristics without SLM.
        Works for well-structured [["key", "value"], ...] arrays.
        """
        try:
            data = json.loads(raw_text)
            if not isinstance(data, list):
                return None

            result = {}
            for pair in data:
                if isinstance(pair, list) and len(pair) >= 2:
                    key = str(pair[0]).strip()
                    val = str(pair[1]).strip()
                    # Try to convert to float
                    try:
                        result[key] = float(val)
                    except ValueError:
                        result[key] = val
            return result if result else None
        except (json.JSONDecodeError, TypeError):
            return None

    def _get_grammar(self):
        """Get llama.cpp grammar for JSON output."""
        from llama_cpp import LlamaGrammar
        return LlamaGrammar.from_string(JSON_GRAMMAR)


# Singleton
slm_service = SLMService()
