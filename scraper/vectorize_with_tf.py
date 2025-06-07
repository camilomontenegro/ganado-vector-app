import numpy as np
from pathlib import Path
from tqdm import tqdm
import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing import image as keras_image
from chromadb import PersistentClient

# Load MobileNetV2 model (no top layer)
model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg')

# Connect to persistent ChromaDB
client = PersistentClient(path="chroma_db")
collection_name = "cattle_brands_tf"

# Optional: Delete existing collection (clean start)
try:
    client.delete_collection(collection_name)
    print("🧹 Existing collection deleted.")
except Exception as e:
    print(f"⚠️ Could not delete collection: {e}")

# Re-create collection
collection = client.get_or_create_collection(name=collection_name)

# Folder with normalized images
IMAGE_FOLDER = Path("scraper/normalized")
images = list(IMAGE_FOLDER.glob("*.jpg"))

print(f"📦 Vectorizing {len(images)} images...")
added = 0

for img_path in tqdm(images):
    try:
        # Load and preprocess image
        img = keras_image.load_img(img_path, target_size=(224, 224))
        x = keras_image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)

        # Get embedding
        embedding = model.predict(x, verbose=0)[0]

        # Store in ChromaDB
        collection.add(
            ids=[img_path.stem],
            embeddings=[embedding.tolist()],
            metadatas=[{"filename": img_path.name}]
        )
        added += 1
    except Exception as e:
        print(f"❌ Error with {img_path.name}: {e}")

print(f"✅ Added {added} embeddings to ChromaDB.")
