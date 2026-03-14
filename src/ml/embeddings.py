import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

PRIORITY_KEYS = [
    "Вид товаров", "Вид продукции", "Назначение", "Тип",
    "Материал", "Объем", "Размер", "Вес",
    "Длина", "Ширина", "Высота", "Диаметр",
    "Количество в упаковке", "Цвет",
]


def build_embedding_text(item: dict) -> str:
    parts = [item["name"], item["category"]]

    chars = item.get("characteristics", {})
    for key in PRIORITY_KEYS:
        val = chars.get(key)
        if val and val != "0.00000":
            parts.append(f"{key}: {val}")

    remaining = [
        (k, v) for k, v in chars.items()
        if k not in PRIORITY_KEYS and v and v != "0.00000"
    ]
    for k, v in remaining[:10]:
        parts.append(f"{k}: {v}")

    text = " | ".join(parts)
    return text[:1000]


class EmbeddingService:
    def __init__(
        self,
        model_name: str,
        api_url: str,
        api_key: str,
        dimensions: int = 1024,
    ) -> None:
        self._client = OpenAI(base_url=api_url, api_key=api_key)
        self._model = model_name
        self._dimensions = dimensions
        logger.info("EmbeddingService initialized: model=%s, api=%s, dims=%d", model_name, api_url, dimensions)

    def encode(self, texts: list[str], batch_size: int = 256) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self._client.embeddings.create(
                input=batch,
                model=self._model,
                encoding_format="float",
                extra_body={"input_type": "passage", "truncate": "NONE"},
            )
            for item in sorted(response.data, key=lambda x: x.index):
                vec = item.embedding[:self._dimensions]
                all_embeddings.append(vec)
        return all_embeddings

    def encode_single(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            input=[text],
            model=self._model,
            encoding_format="float",
            extra_body={"input_type": "query", "truncate": "NONE"},
        )
        vec = response.data[0].embedding[:self._dimensions]
        return vec

    @property
    def vector_size(self) -> int:
        return self._dimensions
