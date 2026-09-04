"""The embedding step: image in, 1280-d unit vector out."""
import io

import numpy as np
import pytest
from PIL import Image

from api.vectorizer import get_image_embedding

EMBEDDING_DIM = 1280  # MobileNetV2 with include_top=False, pooling='avg'


def test_embedding_has_mobilenet_dimensions(sample_image_bytes):
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    assert emb.shape == (EMBEDDING_DIM,)


def test_embedding_is_l2_normalized(sample_image_bytes):
    """Normalization is not cosmetic: the stored vectors are normalized too, so
    an un-normalized query would silently skew every distance."""
    emb = get_image_embedding(io.BytesIO(sample_image_bytes))
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-5)


def test_embedding_is_deterministic(sample_image_bytes):
    """Same bytes must give the same vector, or the self-match test is
    meaningless and results would drift between runs."""
    a = get_image_embedding(io.BytesIO(sample_image_bytes))
    b = get_image_embedding(io.BytesIO(sample_image_bytes))
    np.testing.assert_allclose(a, b, rtol=0, atol=0)


def test_greyscale_image_is_accepted():
    """Uploads are converted to RGB; a single-channel PNG must not blow up."""
    buf = io.BytesIO()
    Image.new("L", (300, 200), color=128).save(buf, format="PNG")
    buf.seek(0)
    emb = get_image_embedding(buf)
    assert emb.shape == (EMBEDDING_DIM,)


def test_non_square_image_is_accepted():
    """Uploads are arbitrary sizes; the resize to 224x224 must handle them."""
    buf = io.BytesIO()
    Image.new("RGB", (800, 300), color=(200, 30, 30)).save(buf, format="JPEG")
    buf.seek(0)
    emb = get_image_embedding(buf)
    assert emb.shape == (EMBEDDING_DIM,)
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-5)
