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
    """Documents the metric, and pins the bug in F10.

    The collection is created without a space setting, so Chroma uses squared L2.
    For unit vectors that ranges 0..4 — NOT 0..1. The frontend computes
    (1 - distance) * 100 as a similarity percentage, which goes negative for
    anything past 1.0. Most of this index is past 1.0.

    When F10 is fixed, this test should be updated alongside it.
    """
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    distances = search_similar(emb, n_results=EXPECTED_EMBEDDINGS)["distances"][0]
    assert max(distances) > 1.0, "expected squared-L2 distances, not cosine"
