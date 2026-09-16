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


def _truncated_jpeg() -> bytes:
    """A real JPEG cut short — what an interrupted upload produces. PIL accepts the
    header then raises OSError partway through, a different path from garbage."""
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (200, 30, 30)).save(buf, format="JPEG")
    full = buf.getvalue()
    return full[: len(full) // 3]


@pytest.mark.parametrize(
    "name,payload",
    [
        ("garbage", b"not an image at all"),
        ("empty", b""),
        ("jpeg magic then junk", b"\xff\xd8\xff" + b"junk" * 20),
    ],
)
def test_unreadable_upload_is_a_client_error(client, name, payload):
    """400, not 500. A mistyped file is the caller's mistake; reporting it as a
    server fault makes error-rate alerting count normal user errors and trains
    you to ignore it."""
    resp = client.post(
        "/search", files={"file": ("x.jpg", io.BytesIO(payload), "image/jpeg")}
    )
    assert resp.status_code == 400, name
    assert resp.json()["detail"] == "No se pudo leer el archivo como imagen. Use un JPG o PNG."


def test_truncated_upload_is_a_client_error(client):
    resp = client.post(
        "/search", files={"file": ("cut.jpg", io.BytesIO(_truncated_jpeg()), "image/jpeg")}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "La imagen parece estar dañada o incompleta."


@pytest.mark.parametrize(
    "payload", [b"not an image at all", b"", None]  # None -> truncated jpeg
)
def test_no_bad_upload_leaks_internals(client, payload):
    """F5's guarantee has to hold on every branch, not just the 500 one."""
    data = _truncated_jpeg() if payload is None else payload
    resp = client.post(
        "/search", files={"file": ("x.jpg", io.BytesIO(data), "image/jpeg")}
    )
    for token in ("SpooledTemporaryFile", "0x", "/Users/", "site-packages",
                  "Traceback", "vectorizer", ".py", "PIL"):
        assert token not in resp.text, f"leaks {token!r}: {resp.text}"


def test_unreadable_upload_is_not_logged_as_an_error(client, caplog):
    """The point of F16: these must stop showing up as server errors."""
    with caplog.at_level(logging.DEBUG, logger="brandmatch.api"):
        client.post("/search", files={"file": ("x.jpg", io.BytesIO(b"nope"), "image/jpeg")})
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    assert "Rejected unreadable upload" in caplog.text


def test_a_genuine_server_fault_still_logs_a_traceback(
    client, monkeypatch, caplog, sample_image_bytes
):
    """F5 must survive F16: a real fault keeps its full detail server-side while
    the client still learns nothing. Without this, narrowing to 400s could quietly
    swallow the errors that actually matter."""
    import api.main

    def boom(*args, **kwargs):
        raise RuntimeError("vector store exploded")

    monkeypatch.setattr(api.main, "search_similar", boom)

    with caplog.at_level(logging.ERROR, logger="brandmatch.api"):
        resp = client.post(
            "/search",
            files={"file": ("1.jpg", io.BytesIO(sample_image_bytes), "image/jpeg")},
        )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "No se pudo procesar la imagen enviada."
    assert "vector store exploded" not in resp.text        # not leaked to the client
    assert "vector store exploded" in caplog.text          # but kept in the log
    assert "Traceback" in caplog.text


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


def test_images_wildcard_is_not_paired_with_credentials(client):
    """The CORS spec forbids Access-Control-Allow-Origin: * together with
    Allow-Credentials: true, and browsers reject the pair outright. /images serves
    the wildcard, so allow_credentials must stay off. This only ever "worked"
    because <img> tags send no credentials."""
    resp = client.get(f"/images/{SAMPLE_NAME}", headers={"Origin": PROD_FRONTEND_ORIGIN})
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in resp.headers


def test_no_endpoint_advertises_credentials(client):
    """Nothing here uses cookies, sessions or Authorization headers. If this starts
    failing, someone re-enabled allow_credentials — which silently invalidates the
    wildcard on /images."""
    for path in ("/", f"/images/{SAMPLE_NAME}"):
        resp = client.get(path, headers={"Origin": PROD_FRONTEND_ORIGIN})
        assert "access-control-allow-credentials" not in resp.headers, path


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
