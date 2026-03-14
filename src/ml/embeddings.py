from sentence_transformers import SentenceTransformer

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
    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str], batch_size: int = 256) -> list[list[float]]:
        embeddings = self._model.encode(texts, batch_size=batch_size, show_progress_bar=True)
        return embeddings.tolist()

    def encode_single(self, text: str) -> list[float]:
        return self._model.encode(text).tolist()

    @property
    def vector_size(self) -> int:
        return self._model.get_sentence_embedding_dimension()
