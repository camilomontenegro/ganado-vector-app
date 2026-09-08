# api/vectorizer.py
import os

# TensorFlow's Linux wheels bundle CUDA and probe for a GPU while building the
# model. On a CPU-only host that probe fails slowly: on Render it burned ~42s of
# every cold start before giving up with
#   "failed call to cuInit: UNKNOWN ERROR (303)".
# Declaring up front that there are no GPUs skips the probe entirely.
#
# Both lines MUST run before tensorflow is imported, or they have no effect.
# setdefault, not assignment, so a host with a real GPU can still override them.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")  # hide the cuFFT/cuDNN noise

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
    embedding = embedding / np.linalg.norm(embedding)
    return embedding
