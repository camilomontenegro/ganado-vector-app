# api/vectorizer.py
import numpy as np
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing import image as keras_image
from PIL import Image
import tensorflow as tf

# Carga el modelo preentrenado una sola vez
model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg')

def get_image_embedding(file) -> np.ndarray:
    """Convierte una imagen a un vector de embedding."""
    img = Image.open(file).convert("RGB")
    img = img.resize((224, 224))
    x = keras_image.img_to_array(img)
    x = np.expand_dims(x, axis=0)
    x = preprocess_input(x)

    embedding = model.predict(x, verbose=0)[0]
    return embedding
