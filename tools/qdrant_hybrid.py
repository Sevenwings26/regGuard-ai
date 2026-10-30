import os
from typing import Any, Dict, List, Optional
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models

DEFAULT_STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "qdrant_storage"))
COLLECTION_NAME = "cbn_regulations"

class QdrantHybridTool:
    """
    Local embedded hybrid retrieval over CBN regulations using Dense (BGE) + Sparse (BM25) with RRF.
    """
    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or DEFAULT_STORAGE_DIR
        if not os.path.exists(self.storage_dir):
            raise FileNotFoundError(f"Qdrant storage not found at {self.storage_dir}. Run scripts/seed_qdrant_corpus.py first.")
        
        self.client = QdrantClient(path=self.storage_dir)
        self.dense_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        self.sparse_model = SparseTextEmbedding("Qdrant/bm25")

    def search(
        self,
        query: str,
        effective_before: Optional[str] = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Executes hybrid dense + sparse retrieval with Reciprocal Rank Fusion (RRF).
        Applies temporal cutoff if effective_before is provided.
        """
        # Embed query
        dense_vec = list(self.dense_model.embed([query]))[0]
        sparse_vec = list(self.sparse_model.embed([query]))[0]

        prefetch = [
            models.Prefetch(
                query=dense_vec.tolist(),
                using="dense",
                limit=top_k * 4
            ),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse_vec.indices.tolist(),
                    values=sparse_vec.values.tolist()
                ),
                using="sparse",
                limit=top_k * 4
            )
        ]

        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k * 4
        )

        output = []
        for point in results.points:
            payload = point.payload or {}
            eff_date = payload.get("effective_date", "9999-12-31")
            
            # Temporal filter: transaction timestamp must be on or after effective date of regulation
            if effective_before and eff_date > effective_before:
                continue

            output.append({
                "clause_id": payload.get("clause_id"),
                "section_title": payload.get("section_title"),
                "text": payload.get("text"),
                "effective_date": eff_date,
                "regulation": payload.get("regulation"),
                "rrf_score": round(float(point.score), 4) if point.score else 0.0
            })
            if len(output) >= top_k:
                break

        return output

_default_hybrid_tool = None

def regulation_search(
    query: str,
    effective_before: Optional[str] = None,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """Functional convenience wrapper for regulation search."""
    global _default_hybrid_tool
    if _default_hybrid_tool is None:
        _default_hybrid_tool = QdrantHybridTool()
    return _default_hybrid_tool.search(query, effective_before, top_k)
