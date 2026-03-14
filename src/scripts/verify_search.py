import logging
import sys
from pathlib import Path
from qdrant_client import QdrantClient

# Add src to sys path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.config import settings
from src.data_access.cte_repo import CTERepository
from src.ml.embedder import Embedder

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def test_search(query: str):
    logger.info(f"Testing search for query: '{query}'")

    # 1. Setup
    qdrant_client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    embedder = Embedder()

    repo = CTERepository(
        qdrant_client=qdrant_client,
        collection_name=settings.qdrant_collection,
        embedding_dim=settings.embedding_dim,
    )

    # 2. Encode query
    logger.info("Encoding query...")
    query_vector = embedder.encode_single(query)

    # 3. Search
    logger.info("Searching in Qdrant...")
    results = repo.search(query_vector=query_vector, limit=5)

    # 4. Print results
    print("\n" + "=" * 50)
    print(f"SEARCH RESULTS FOR: '{query}'")
    print("=" * 50)
    if not results:
        print("No results found.")
    for i, res in enumerate(results):
        print(f"{i + 1}. [{res['cosine_score']}] {res['name']}")
        print(f"   Category: {res['category']}")
        print(f"   CTE ID: {res['cte_id']}")
        print("-" * 30)


if __name__ == "__main__":
    # Test queries
    queries = [
        "План эвакуации",
    ]

    for q in queries:
        test_search(q)
