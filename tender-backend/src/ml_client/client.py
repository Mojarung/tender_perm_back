"""HTTP client for communicating with the ML Worker service."""

import httpx
import logging

from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MLClient:
    """Async client for the ML Worker internal API."""

    def __init__(self) -> None:
        self.base_url = settings.ml_service_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding vector for text via ML Worker."""
        client = await self._get_client()
        response = await client.post(
            "/internal/ml/embed",
            json={"text": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    async def parse_characteristics(self, raw_text: str) -> dict:
        """Parse raw characteristics array into structured JSON via SLM."""
        client = await self._get_client()
        response = await client.post(
            "/internal/ml/parse-characteristics",
            json={"raw_text": raw_text},
        )
        response.raise_for_status()
        return response.json()["parsed_json"]

    async def detect_outliers(self, prices: list[float]) -> dict:
        """Detect price outliers via IsolationForest."""
        client = await self._get_client()
        response = await client.post(
            "/internal/ml/detect-outliers",
            json={"prices": prices},
        )
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        """Check if ML Worker is healthy."""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception:
            return False


# Singleton instance
ml_client = MLClient()
