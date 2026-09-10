# api/main.py
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.vectorizer import get_image_embedding
from api.search import search_similar
from api.chroma_client import collection
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path

logger = logging.getLogger("brandmatch.api")

app = FastAPI()

# Get the absolute path to the normalized images directory
NORMALIZED_DIR = Path(__file__).resolve().parent.parent / "scraper" / "normalized"
NORMALIZED_DIR = NORMALIZED_DIR.resolve()

# Permitir CORS si el frontend se conecta desde otro puerto
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",                   # local dev: python -m http.server 3000
        "https://brandmatch-static.onrender.com",  # Render Static Site
        ],
    # allow_credentials is deliberately OFF. Nothing here uses cookies, sessions
    # or Authorization headers, so it bought nothing — and it actively broke
    # /images, which serves `Access-Control-Allow-Origin: *`. The CORS spec
    # forbids pairing a wildcard origin with Allow-Credentials, and browsers
    # reject the combination outright. It only appeared to work because <img>
    # tags send no credentials.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The frontend is served separately (frontend/ is plain static HTML), so this
# app never serves HTML. Root is a health check, not a page.


@app.api_route("/", methods=["GET", "HEAD"])
def health():
    """Liveness probe for Render, and a cheap way to wake a sleeping instance.

    Reports the embedding count rather than a bare "ok" so the check also proves
    the vector store actually loaded — an API that answers but has an empty
    ChromaDB is worse than one that is plainly down.

    HEAD is listed explicitly. FastAPI's @app.get() registers GET only, unlike
    plain Starlette which adds HEAD alongside it — so this route used to answer
    Render's port scanner with 405, and any uptime monitor defaulting to HEAD
    would have reported the service as down.
    """
    return {"status": "ok", "indexed": collection.count()}


@app.post("/search")
async def search_image(file: UploadFile = File(...), n_results: int = 5):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
    try:
        embedding = get_image_embedding(file.file)
        results = search_similar(embedding, n_results=n_results)
        
        # Convert to list of results
        matches = []
        for i in range(len(results["ids"][0])):
            matches.append({                "filename": results["metadatas"][0][i]["filename"],
                "id": results["ids"][0][i],
                "distance": float(results["distances"][0][i]),
                "imageUrl": f"/images/{results['metadatas'][0][i]['filename']}"
            })
        
        return {"matches": matches}
    except Exception:
        # Log the full traceback server-side, return nothing useful to an attacker.
        # The old version interpolated the exception straight into the response,
        # which leaked internals — a corrupt upload returned
        # "cannot identify image file <tempfile.SpooledTemporaryFile object at 0x...>",
        # exposing an object type and a memory address.
        logger.exception("Failed to process uploaded image %r", file.filename)
        raise HTTPException(
            status_code=500,
            detail="Could not process the uploaded image.",
        )

# Mount the normalized images directory using absolute path
from fastapi.staticfiles import StaticFiles
app.mount("/images", StaticFiles(directory=str(NORMALIZED_DIR)), name="images")

# Thumbnails are public brand pictures with nothing sensitive in them, and the
# frontend is a separate Render Static Site, so /images is deliberately readable
# from any origin — unlike /search, which stays on the allowlist above.
#
# This wildcard is only valid because allow_credentials is False; pairing the two
# is forbidden by the CORS spec and browsers refuse it.
@app.middleware("http")
async def add_cors_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/images"):
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response


