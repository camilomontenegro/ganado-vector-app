# api/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.vectorizer import get_image_embedding
from api.search import search_similar

app = FastAPI()

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
async def search_image(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
    try:
        embedding = get_image_embedding(file.file)
        results = search_similar(embedding)
        return {
            "result": results["metadatas"][0][0],
            "id": results["ids"][0][0],
            "distance": results["distances"][0][0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {e}")


