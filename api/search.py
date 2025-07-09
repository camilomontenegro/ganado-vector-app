# api/search.py
from api.chroma_client import collection
import numpy as np

def search_similar(embedding: np.ndarray, n_results: int = 1):
    """Consulta ChromaDB para encontrar las imágenes más similares."""
    results = collection.query(
        query_embeddings=[embedding.tolist()],
        n_results=n_results
    )
    return results
