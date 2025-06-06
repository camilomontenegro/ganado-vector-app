import os
import numpy as np
from PIL import Image
from pathlib import Path
from tqdm import tqdm
import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing import image as keras_image
from chromadb import Client
from chromadb.config import Settings

# Load MobileNetV2 (no top layer)
model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg')

# Initialize ChromaDB
chroma_client = Client(Settings(anonymized_telemetry=False))
collection = chroma_client.get_or_create_collection(name="cattle_brands_tf")

# Input folder
IMAGE_FOLDER = Path("normalized")
images = list(IMAGE_FOLDER.glob("*.jpg"))

print(f"📦 Vectorizing {len(images)} images...")

for img_path in tqdm(images):
    try:
        # Load and preprocess image
        img = keras_image.load_img(img_path, target_size=(224, 224))
        x = keras_image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)

        # Generate embedding
        embedding = model.predict(x, verbose=0)[0]

        # Store in Chroma
        collection.add(
            ids=[img_path.stem],
            embeddings=[embedding.tolist()],
            metadatas=[{"filename": img_path.name}]
        )
    except Exception as e:
        print(f"❌ Error with {img_path.name}: {e}")
