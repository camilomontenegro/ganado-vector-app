"""Shared fixtures.

These tests run against the REAL committed ChromaDB store (78 embeddings) rather
than a synthetic fixture. That is deliberate: the index is committed, stable, and
is the thing we actually ship, so testing against it catches drift between the
scraper pipeline and the query path. Every query here is read-only.

Note: merely opening the Chroma client rewrites files under chroma_db/, so
running the suite dirties tracked binaries. That is feature F6, not a test bug.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
NORMALIZED_DIR = REPO_ROOT / "scraper" / "normalized"

# api/chroma_client.py opens "chroma_db" as a RELATIVE path, so the suite is only
# correct when the process runs from the repository root. Fail loudly rather than
# silently testing against an empty database.
if pathlib.Path.cwd().resolve() != REPO_ROOT:
    raise RuntimeError(
        f"pytest must run from the repository root ({REPO_ROOT}); "
        f"got {pathlib.Path.cwd()}. Otherwise chroma_db resolves elsewhere and "
        f"every search returns nothing."
    )

sys.path.insert(0, str(REPO_ROOT))

# A brand image that is definitely in the index, used for the self-match check.
SAMPLE_NAME = "1.jpg"
SAMPLE_PATH = NORMALIZED_DIR / SAMPLE_NAME


@pytest.fixture(scope="session")
def sample_image_bytes() -> bytes:
    return SAMPLE_PATH.read_bytes()


@pytest.fixture(scope="session")
def collection():
    from api.chroma_client import collection as c
    return c


@pytest.fixture(scope="session")
def client():
    """TestClient over the real app. Session-scoped: importing api.main loads
    MobileNetV2, which is slow enough that per-test setup would hurt."""
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c
