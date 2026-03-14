import os

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)


def _patch_no_proxy() -> None:
    """Ensure localhost/127.0.0.1 bypass any VPN/corporate proxy."""
    existing = os.environ.get("NO_PROXY", "")
    needed = {"localhost", "127.0.0.1"}
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    for h in needed:
        if h not in parts:
            parts.append(h)
    os.environ["NO_PROXY"] = ",".join(parts)
    os.environ["no_proxy"] = ",".join(parts)


class QdrantRepository:
    def __init__(self, host: str, port: int, collection: str) -> None:
        _patch_no_proxy()
        self._client = QdrantClient(host=host, port=port)
        self._collection = collection

    def ensure_collection(self, vector_size: int) -> None:
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection not in collections:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )

    def has_collection(self) -> bool:
        collections = [c.name for c in self._client.get_collections().collections]
        return self._collection in collections

    def upsert_batch(self, points: list[PointStruct]) -> None:
        self._client.upsert(
            collection_name=self._collection,
            points=points,
        )

    def search(
        self,
        vector: list[float],
        category: str | None = None,
        limit: int = 50,
        score_threshold: float = 0.70,
    ) -> list[dict]:
        import logging
        _log = logging.getLogger(__name__)

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

        # First try without score_threshold to see raw results
        response = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
        )
        all_points = response.points
        _log.info("query_points returned %d raw results", len(all_points))
        if all_points:
            _log.info("top score=%.4f, bottom score=%.4f",
                       all_points[0].score, all_points[-1].score)

        # Manual threshold filter
        results = [p for p in all_points if p.score >= score_threshold]
        _log.info("after threshold %.2f: %d results", score_threshold, len(results))

        return [
            {
                "cte_id": point.payload["cte_id"],
                "name": point.payload["name"],
                "category": point.payload["category"],
                "cosine_score": point.score,
                "payload": point.payload,
            }
            for point in results
        ]

    def get_vector_by_cte_id(self, cte_id: int) -> list[float] | None:
        points = self._client.retrieve(
            collection_name=self._collection,
            ids=[cte_id],
            with_vectors=True,
            with_payload=False,
        )
        if not points:
            return None

        vector = points[0].vector
        if vector is None:
            return None

        if isinstance(vector, dict):
            first_vector = next(iter(vector.values()), None)
            return first_vector

        return vector

    def collection_size(self) -> int:
        info = self._client.get_collection(self._collection)
        return info.points_count or 0
