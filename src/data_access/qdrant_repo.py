from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)


class QdrantRepository:
    def __init__(self, host: str, port: int, collection: str) -> None:
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

        results = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
        ).points

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

    def collection_size(self) -> int:
        info = self._client.get_collection(self._collection)
        return info.points_count or 0
