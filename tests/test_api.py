"""The HTTP layer: /search, /images, and the CORS setup the two Render services
depend on (the frontend is a separate Static Site, so every call is cross-origin).
"""
import io
import logging

import pytest
from PIL import Image

from tests.conftest import NORMALIZED_DIR, SAMPLE_NAME


def _allowed_origins(app):
    """Read the origins actually configured on CORSMiddleware, so this test does
    not hardcode hostnames that feature F3 is expected to change."""
    for mw in app.user_middleware:
        if mw.cls.__name__ == "CORSMiddleware":
            kwargs = getattr(mw, "kwargs", None) or {}
            return list(kwargs.get("allow_origins", []))
    return []


# ─── /search ─────────────────────────────────────────────────────────────────

def test_search_returns_matches(client, sample_image_bytes):
    resp = client.post(
        "/search?n_results=5",
        files={"file": (SAMPLE_NAME, io.BytesIO(sample_image_bytes), "image/jpeg")},
    )
    assert resp.status_code == 200
    assert len(resp.json()["matches"]) == 5


def test_search_honours_n_results(client, sample_image_bytes):
    resp = client.post(
        "/search?n_results=3",
        files={"file": (SAMPLE_NAME, io.BytesIO(sample_image_bytes), "image/jpeg")},
    )
    assert len(resp.json()["matches"]) == 3


def test_search_match_shape(client, sample_image_bytes):
    """The frontend reads exactly these four keys; renaming one breaks the UI
    silently, with no server-side error."""
    resp = client.post(
        "/search?n_results=1",
        files={"file": (SAMPLE_NAME, io.BytesIO(sample_image_bytes), "image/jpeg")},
    )
    match = resp.json()["matches"][0]
    assert set(match) == {"filename", "id", "distance", "imageUrl"}
    assert match["imageUrl"] == f"/images/{match['filename']}"
    assert isinstance(match["distance"], float)


def test_search_top_match_is_the_uploaded_image(client, sample_image_bytes):
    """End-to-end version of the self-match check, through HTTP."""
    resp = client.post(
        "/search?n_results=5",
        files={"file": (SAMPLE_NAME, io.BytesIO(sample_image_bytes), "image/jpeg")},
    )
    top = resp.json()["matches"][0]
    assert top["filename"] == SAMPLE_NAME
    assert top["distance"] == pytest.approx(0.0, abs=1e-4)


def test_every_returned_filename_exists_on_disk(client, sample_image_bytes):
    """A match pointing at a missing file renders as a broken card in the UI."""
    resp = client.post(
        "/search?n_results=10",
        files={"file": (SAMPLE_NAME, io.BytesIO(sample_image_bytes), "image/jpeg")},
    )
    for match in resp.json()["matches"]:
        assert (NORMALIZED_DIR / match["filename"]).is_file(), match["filename"]


def test_search_rejects_non_image(client):
    resp = client.post(
        "/search",
        files={"file": ("notes.txt", io.BytesIO(b"not an image"), "text/plain")},
    )
    assert resp.status_code == 400


def test_corrupt_image_does_not_leak_internals(client):
    """The old handler interpolated the exception into the response, so a corrupt
    upload returned the tempfile object's type and memory address. Anything that
    names a path, module or object is a disclosure."""
    resp = client.post(
        "/search",
        files={"file": ("broken.jpg", io.BytesIO(b"\xff\xd8\xff garbage"), "image/jpeg")},
    )
    assert resp.status_code == 500
    body = resp.text
    for token in ("SpooledTemporaryFile", "0x", "/Users/", "site-packages",
                  "Traceback", "vectorizer", ".py", "PIL"):
        assert token not in body, f"response leaks {token!r}: {body}"


def test_corrupt_image_returns_a_generic_message(client):
    resp = client.post(
        "/search",
        files={"file": ("broken.jpg", io.BytesIO(b"not an image at all"), "image/jpeg")},
    )
    assert resp.json()["detail"] == "Could not process the uploaded image."


def test_failure_is_logged_server_side(client, caplog):
    """The detail has to survive somewhere — losing it entirely would trade a
    disclosure bug for an undebuggable one."""
    with caplog.at_level(logging.ERROR, logger="brandmatch.api"):
        client.post(
            "/search",
            files={"file": ("broken.jpg", io.BytesIO(b"nope"), "image/jpeg")},
        )
    assert any(r.levelname == "ERROR" for r in caplog.records)
    assert "UnidentifiedImageError" in caplog.text


def test_search_accepts_png_upload(client):
    """The frontend allows JPG or PNG; PNG must survive the RGB conversion."""
    buf = io.BytesIO()
    Image.new("RGB", (500, 400), color=(10, 10, 10)).save(buf, format="PNG")
    buf.seek(0)
    resp = client.post(
        "/search?n_results=2",
        files={"file": ("brand.png", buf, "image/png")},
    )
    assert resp.status_code == 200
    assert len(resp.json()["matches"]) == 2


# ─── /images ─────────────────────────────────────────────────────────────────

def test_images_serves_a_known_file(client):
    resp = client.get(f"/images/{SAMPLE_NAME}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"


def test_images_404s_on_unknown_file(client):
    assert client.get("/images/definitely-not-here.jpg").status_code == 404


def test_images_are_readable_cross_origin(client):
    """The Static Site loads these <img> tags from a different origin than the
    Web Service, so the wildcard header on /images is load-bearing."""
    resp = client.get(f"/images/{SAMPLE_NAME}")
    assert resp.headers.get("access-control-allow-origin") == "*"


# ─── routing and CORS ────────────────────────────────────────────────────────

def test_root_is_a_health_check(client):
    """Root is a liveness probe, not a page — the frontend is a separate Render
    Static Site. Render's health check may point here, so a 404 would fail the
    deploy."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_head_root_is_allowed(client):
    """Render's port scanner probes with HEAD. FastAPI's @app.get() registers GET
    only — unlike plain Starlette — so this returned 405 and polluted the deploy
    logs. Any uptime monitor defaulting to HEAD would have read the service as
    down."""
    resp = client.head("/")
    assert resp.status_code == 200


def test_head_root_sends_no_body(client):
    """HEAD must carry the same headers as GET but no body, per HTTP semantics."""
    head = client.head("/")
    get = client.get("/")
    assert head.content == b""
    assert head.headers["content-type"] == get.headers["content-type"]


def test_health_reports_the_embedding_count(client):
    """A bare 'ok' would still pass with an empty ChromaDB, which is the exact
    failure this app is prone to when started from the wrong directory."""
    assert client.get("/").json()["indexed"] == 78


def test_no_html_is_served(client):
    """Guards against the F1 regression: the API must never mount static files
    or return a page. If this starts returning HTML, someone re-added the mount."""
    assert "text/html" not in client.get("/").headers["content-type"]


def test_only_expected_routes_are_exposed(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths == {"/", "/search"}


def test_cors_allows_a_configured_origin(client):
    origins = _allowed_origins(client.app)
    assert origins, "CORSMiddleware is configured with no origins"
    resp = client.options(
        "/search",
        headers={
            "Origin": origins[0],
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == origins[0]


def test_cors_rejects_an_unlisted_origin(client):
    resp = client.options(
        "/search",
        headers={
            "Origin": "https://not-your-frontend.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") is None


# ─── deployed origins (F3) ───────────────────────────────────────────────────
# Hardcoded on purpose. Everything above reads origins off the app so it stays
# agnostic; these two assert the specific Render URLs the deployment actually
# uses, so a stale allowlist fails here instead of in a user's browser.

PROD_FRONTEND_ORIGIN = "https://brandmatch-static.onrender.com"   # Render Static Site
LOCAL_FRONTEND_ORIGIN = "http://localhost:3000"                   # python -m http.server 3000


@pytest.mark.parametrize("origin", [PROD_FRONTEND_ORIGIN, LOCAL_FRONTEND_ORIGIN])
def test_real_frontend_origins_are_allowed(client, origin):
    resp = client.options(
        "/search",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == origin


def test_stale_origins_are_no_longer_allowed(client):
    """brandmatch.onrender.com and the Astro dev port 4321 were both in the
    allowlist and neither exists. Guard against them creeping back."""
    for origin in ("https://brandmatch.onrender.com", "http://localhost:4321"):
        resp = client.options(
            "/search",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert resp.headers.get("access-control-allow-origin") is None, origin
