"""CTE catalog repository — loads cte.json, builds embeddings, manages Qdrant."""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

# Batch size for Qdrant upserts
UPSERT_BATCH_SIZE = 256


def _chars_to_dict(characteristics: list[list[str]]) -> dict[str, str]:
    """Convert [[key, val], ...] to {key: val}."""
    result: dict[str, str] = {}
    for pair in characteristics:
        if len(pair) >= 2:
            result[pair[0]] = pair[1]
    return result


def _build_embedding_text(item: dict[str, Any]) -> str:
    """Build rich text for embedding from CTE item fields."""
    parts = [item["Наименование СТЕ"], item.get("Категория", "")]
    attrs = item.get("_attributes", {})
    for key, val in list(attrs.items())[:10]:  # top 10 attributes
        parts.append(f"{key}: {val}")
    return " | ".join(parts)


class CTERepository:
    """Manages CTE catalog: loading, embedding, Qdrant storage & search."""

    def __init__(
        self,
        qdrant_client: QdrantClient,
        collection_name: str,
        embedding_dim: int = 1024,
    ):
        self.client = qdrant_client
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self._items: list[dict[str, Any]] = []
        self._id_to_item: dict[int, dict[str, Any]] = {}

    def load_cte_data(self, file_path: Path, max_items: int = 0) -> list[dict[str, Any]]:
        """Load cte.json and preprocess characteristics. max_items=0 means all."""
        logger.info("Loading CTE catalog from %s ...", file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        logger.info("Raw JSON loaded: %d total CTE items", len(raw))
        if max_items > 0:
            raw = raw[:max_items]
            logger.info("LIMITED to %d items for fast startup", max_items)

        self._items = []
        for item in raw:
            processed = {
                "Идентификатор СТЕ": item["Идентификатор СТЕ"],
                "Наименование СТЕ": item["Наименование СТЕ"],
                "Категория": item.get("Категория", ""),
                "Производитель": item.get("Производитель", ""),
                "_attributes": _chars_to_dict(item.get("характеристики СТЕ", [])),
            }
            self._items.append(processed)
            self._id_to_item[processed["Идентификатор СТЕ"]] = processed

        return self._items

    def get_items(self) -> list[dict[str, Any]]:
        return self._items

    def get_item_by_id(self, cte_id: int) -> dict[str, Any] | None:
        return self._id_to_item.get(cte_id)

    def ensure_collection(self) -> None:
        """Create Qdrant collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name in collections:
            logger.info("Collection '%s' already exists", self.collection_name)
            return

        logger.info(
            "Creating collection '%s' (dim=%d, cosine)",
            self.collection_name,
            self.embedding_dim,
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.embedding_dim, distance=Distance.COSINE
            ),
        )

    def collection_has_data(self) -> bool:
        """Check if the collection already has points."""
        try:
            info = self.client.get_collection(self.collection_name)
            return info.points_count > 0
        except Exception:
            return False

    def upsert_items(self, embedder) -> None:
        """Embed all CTE items and upsert into Qdrant in batches."""
        if not self._items:
            raise ValueError("No CTE items loaded. Call load_cte_data() first.")

        self.ensure_collection()

        if self.collection_has_data():
            logger.info("Collection already has data, skipping upsert")
            return

        total = len(self._items)
        logger.info("Starting embedding of %d CTE items ...", total)

        texts = [_build_embedding_text(item) for item in self._items]

        # Embed in batches
        all_embeddings = []
        batch_size = 256
        num_batches = (len(texts) + batch_size - 1) // batch_size
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_embeddings = embedder.encode(batch_texts)
            all_embeddings.append(batch_embeddings)
            done = min(i + batch_size, total)
            logger.info("[Embedding] %d / %d done (batch %d/%d)", done, total, i // batch_size + 1, num_batches)

        embeddings = np.vstack(all_embeddings)

        # Upsert in batches
        total_upserted = 0
        for i in range(0, len(self._items), UPSERT_BATCH_SIZE):
            batch_items = self._items[i : i + UPSERT_BATCH_SIZE]
            batch_vectors = embeddings[i : i + UPSERT_BATCH_SIZE]

            points = []
            for j, item in enumerate(batch_items):
                point = PointStruct(
                    id=item["Идентификатор СТЕ"],
                    vector=batch_vectors[j].tolist(),
                    payload={
                        "cte_id": item["Идентификатор СТЕ"],
                        "name": item["Наименование СТЕ"],
                        "category": item["Категория"],
                        "manufacturer": item["Производитель"],
                        "attributes": item["_attributes"],
                    },
                )
                points.append(point)

            self.client.upsert(
                collection_name=self.collection_name,
                wait=True,
                points=points,
            )
            total_upserted += len(points)
            logger.info("Upserted %d / %d points", total_upserted, len(self._items))

        logger.info("CTE catalog upserted to Qdrant: %d points", total_upserted)

    def search(
        self,
        query_vector: list[float],
        category: str | None = None,
        limit: int = 20,
        score_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        Search Qdrant with optional category filter (hybrid search).

        Returns list of dicts with payload + score.
        """
        query_filter = None
        if category:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="category",
                        match=MatchValue(value=category),
                    )
                ]
            )

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        search_results = []
        for hit in results:
            payload = hit.payload or {}
            search_results.append(
                {
                    "cte_id": payload.get("cte_id"),
                    "name": payload.get("name", ""),
                    "category": payload.get("category", ""),
                    "manufacturer": payload.get("manufacturer", ""),
                    "attributes": payload.get("attributes", {}),
                    "cosine_score": round(hit.score, 4),
                }
            )

        return search_results
