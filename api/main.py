# api/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.vectorizer import get_image_embedding
from api.search import search_similar
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path

app = FastAPI()

# Get the absolute path to the normalized images directory
NORMALIZED_DIR = Path(__file__).resolve().parent.parent / "scraper" / "normalized"
NORMALIZED_DIR = NORMALIZED_DIR.resolve()

# Permitir CORS si el frontend se conecta desde otro puerto
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "✅ Cattle Brand Vector API is live"}

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {e}")

# Mount the normalized images directory using absolute path
from fastapi.staticfiles import StaticFiles
app.mount("/images", StaticFiles(directory=str(NORMALIZED_DIR)), name="images")

# Add CORS headers for images
@app.middleware("http")
async def add_cors_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/images"):
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response


