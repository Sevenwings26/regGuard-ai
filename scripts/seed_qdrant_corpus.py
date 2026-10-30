import json
import os
import shutil
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
STORAGE_DIR = os.path.join(DATA_DIR, "qdrant_storage")
JSON_PATH = os.path.join(DATA_DIR, "cbn_regulations.json")
COLLECTION_NAME = "cbn_regulations"

def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        clauses = json.load(f)

    print(f"Loaded {len(clauses)} CBN regulation clauses.")
    print("Initializing FastEmbed models (Dense: BAAI/bge-small-en-v1.5, Sparse: Qdrant/bm25)...")
    dense_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")

    # Wipe and recreate persistent storage directory
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)
    os.makedirs(STORAGE_DIR, exist_ok=True)

    client = QdrantClient(path=STORAGE_DIR)

    # Configure collection with both named dense and sparse vectors
    client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(size=384, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams()
        }
    )

    texts = [f"{c['section_title']} - {c['text']}" for c in clauses]
    
    print("Generating dense and sparse embeddings...")
    dense_embeddings = list(dense_model.embed(texts))
    sparse_embeddings = list(sparse_model.embed(texts))

    points = []
    for idx, (clause, d_vec, s_vec) in enumerate(zip(clauses, dense_embeddings, sparse_embeddings)):
        point = models.PointStruct(
            id=idx,
            vector={
                "dense": d_vec.tolist(),
                "sparse": models.SparseVector(
                    indices=s_vec.indices.tolist(),
                    values=s_vec.values.tolist()
                )
            },
            payload=clause
        )
        points.append(point)

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"✓ Ingested and indexed {len(points)} clauses into local Qdrant collection '{COLLECTION_NAME}'.")
    client.close()

if __name__ == "__main__":
    main()
