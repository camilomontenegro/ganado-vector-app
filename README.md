# 🐮 BrandMatch: Cattle Brand Image Search

Welcome! This is my full-stack project for searching and matching cattle brand images using deep learning and vector search. Below, I’ll walk you through how everything works, how to set it up, and how to use it.

---

## 🚀 What is BrandMatch?
BrandMatch lets you upload a cattle brand image and instantly find the most similar brands in my database. It uses MobileNetV2 for image embeddings and ChromaDB for fast similarity search. The frontend is built with Astro for a modern, responsive UI.

---

## 🗂️ Project Structure

```
/
├── api/           # FastAPI backend (image search API)
├── scraper/       # Scripts for building the image/vector database
├── chroma_db/     # Persistent vector database (auto-generated)
├── frontend/      # Astro frontend (UI)
```

---

## 🧩 How it Works

### 1. Scraper: Building the Database
- **scrape_duckduckgo.py**: Downloads cattle brand images from DuckDuckGo.
- **normalize_images.py**: Resizes and standardizes all images.
- **vectorize_with_tf.py**: Uses MobileNetV2 to turn each image into a vector (embedding) and stores it in ChromaDB.

### 2. Backend API (FastAPI)
- **main.py**: Exposes a `/search` endpoint. When you upload an image, it:
  1. Vectorizes the image using MobileNetV2 (same as the scraper).
  2. Searches ChromaDB for the most similar images.
  3. Returns the top matches (with similarity scores and image URLs).
- **vectorizer.py**: Handles image preprocessing and embedding.
- **search.py**: Handles vector search in ChromaDB.
- **chroma_client.py**: Sets up the ChromaDB client and collection.

### 3. Frontend (Astro)
- **ImageUploader.astro**: Main UI for uploading images, previewing, and showing results.
- **ImageUploader.js**: Handles image preview, form submission, and result rendering.
- **ImageUploader.css**: Styles for a clean, modern look.
- **pages/about.astro & contact.astro**: Info and contact pages.

---

## 🛠️ How to Run It

### 1. Install dependencies
- Backend: `pip install -r requirements.txt` (make sure you have Python 3.10+)
- Frontend: `cd frontend && npm install`

### 2. Prepare the database
- Download images: `python scraper/scrape_duckduckgo.py`
- Normalize images: `python scraper/normalize_images.py`
- Vectorize: `python scraper/vectorize_with_tf.py`

### 3. Start the backend
```sh
$env:PYTHONPATH="."
uvicorn api.main:app --reload
```

### 4. Start the frontend
```sh
cd frontend
npm run dev
```

---

## 🖼️ How to Use
1. Go to [localhost:4321](http://localhost:4321) in your browser.
2. Upload a cattle brand image (JPG/PNG).
3. Set how many matches you want (1-10).
4. Click "Find Matches".
5. See the most similar brands, with images and similarity scores.

---

## 🤖 How the Search Works
- I use MobileNetV2 (pre-trained on ImageNet, no top layer) to turn images into 1280-dim vectors.
- All database images are vectorized and stored in ChromaDB.
- When you upload an image, I vectorize it the same way and search for the closest vectors in ChromaDB.
- The API returns the top N matches, and the frontend displays them in a grid.

---

## 📝 Customization & Extending
- Want to use your own images? Just add them to `scraper/images/`, normalize, and re-vectorize.
- You can swap out MobileNetV2 for another model in `vectorizer.py` and `vectorize_with_tf.py`.
- The frontend is fully customizable with Astro and CSS modules.

---

## 📦 Tech Stack
- **Frontend:** Astro, Vanilla JS, CSS
- **Backend:** FastAPI, Python, ChromaDB, TensorFlow/Keras
- **Database:** ChromaDB (vector search)

---

## 🙋‍♂️ Questions?
Open an issue or reach out! I’m happy to help you get started or answer any questions about the code or setup.

---

Enjoy using BrandMatch! 🐮
