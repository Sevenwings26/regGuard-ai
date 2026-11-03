import json
import os
import shutil
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models
from dotenv import load_dotenv

# Load .env
_dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(_dotenv_path):
    load_dotenv(_dotenv_path, override=False)
else:
    load_dotenv(override=False)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
STORAGE_DIR = os.path.join(DATA_DIR, "qdrant_storage")
JSON_PATH = os.path.join(DATA_DIR, "cbn_regulations.json")
COLLECTION_NAME = "cbn_regulations"

DENSE_MODEL_NAME = os.getenv("EMBEDDING_DENSE_MODEL", "BAAI/bge-small-en-v1.5")
SPARSE_MODEL_NAME = os.getenv("EMBEDDING_SPARSE_MODEL", "Qdrant/bm25")

def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        clauses = json.load(f)

    print(f"Loaded {len(clauses)} CBN regulation clauses.")
    print(f"Initializing FastEmbed models (Dense: {DENSE_MODEL_NAME}, Sparse: {SPARSE_MODEL_NAME})...")
    dense_model = TextEmbedding(DENSE_MODEL_NAME)
    sparse_model = SparseTextEmbedding(SPARSE_MODEL_NAME)

    # Wipe and recreate persistent storage directory
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)
    os.makedirs(STORAGE_DIR, exist_ok=True)

    client = QdrantClient(path=STORAGE_DIR)

    # Dynamically determine vector dimensions from sample embedding
    sample_vec = list(dense_model.embed(["probe"]))[0]
    vector_dim = len(sample_vec)
    print(f"Configuring dense vector dimension: {vector_dim}")

    # Configure collection with both named dense and sparse vectors
    client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(size=vector_dim, distance=models.Distance.COSINE)
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
