"""The vector-search step, below the HTTP layer."""
import io

import pytest

from api.search import search_similar
from api.vectorizer import get_image_embedding

EXPECTED_EMBEDDINGS = 78


def test_collection_is_populated(collection):
    assert collection.count() == EXPECTED_EMBEDDINGS


def test_search_returns_requested_number_of_results(sample_image_bytes):
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    results = search_similar(emb, n_results=5)
    assert len(results["ids"][0]) == 5


def test_image_is_its_own_nearest_neighbour(sample_image_bytes):
    """The core correctness check. Vectorizing an indexed image at query time
    must reproduce the vector the scraper stored, so it ranks itself first at
    distance ~0. If this fails, query-time and index-time preprocessing have
    diverged and every result is suspect."""
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    results = search_similar(emb, n_results=5)
    assert results["metadatas"][0][0]["filename"] == "1.jpg"
    assert results["distances"][0][0] == pytest.approx(0.0, abs=1e-4)


def test_distances_are_ascending(sample_image_bytes):
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    distances = search_similar(emb, n_results=10)["distances"][0]
    assert distances == sorted(distances)


def test_every_result_carries_a_filename(sample_image_bytes):
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    results = search_similar(emb, n_results=10)
    for meta in results["metadatas"][0]:
        assert meta.get("filename")


def test_distances_exceed_one_so_they_are_not_cosine(sample_image_bytes):
    """Pins the metric the frontend's percentage formula depends on.

    The collection is created without a space setting, so Chroma uses squared L2.
    For unit vectors that ranges 0..2 — NOT 0..1. frontend/script.js therefore
    computes (1 - distance / 2) * 100, not (1 - distance) * 100.

    If this ever starts failing, the metric changed and that formula is wrong.
    """
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    distances = search_similar(emb, n_results=EXPECTED_EMBEDDINGS)["distances"][0]
    assert max(distances) > 1.0, "expected squared-L2 distances, not cosine"


def test_embeddings_are_non_negative():
    """The guarantee that makes the frontend percentage safe.

    MobileNetV2 with include_top=False ends in ReLU6, so every feature is >= 0.
    Non-negative unit vectors have cosine in [0,1], which bounds squared-L2
    distance to [0,2], which bounds (1 - d/2) * 100 to 0-100%.

    Swap in a model with signed features and this fails — at which point the
    frontend needs a clamp.
    """
    import numpy as np
    from api.chroma_client import collection

    embeddings = np.array(collection.get(include=["embeddings"])["embeddings"])
    assert embeddings.min() >= 0.0


def test_no_pair_in_the_index_would_render_a_negative_percentage():
    """End-to-end guard for F10, over every pair rather than one query.

    Checks the whole 78x78 distance matrix, so a single unlucky image cannot
    reintroduce a negative percentage unnoticed.
    """
    import numpy as np
    from api.chroma_client import collection

    embeddings = np.array(collection.get(include=["embeddings"])["embeddings"])
    worst_distance = float((2 - 2 * (embeddings @ embeddings.T)).max())

    assert worst_distance <= 2.0, f"distance {worst_distance} exceeds the L2 bound"
    assert (1 - worst_distance / 2) * 100 >= 0.0

    # The formula the bug replaced would have gone badly negative here.
    assert (1 - worst_distance) * 100 < 0, "regression fixture no longer meaningful"
