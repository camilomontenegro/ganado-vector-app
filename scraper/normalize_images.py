from PIL import Image
from pathlib import Path
import os
from tqdm import tqdm

# Input/output folders
INPUT_FOLDER = Path("images")
OUTPUT_FOLDER = Path("normalized")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# Standard size for models like CLIP, ResNet
SIZE = (224, 224)

# Normalize each image
for image_path in tqdm(list(INPUT_FOLDER.glob("*"))):
    output_path = OUTPUT_FOLDER / (image_path.stem + ".jpg")

    if output_path.exists():
        continue  # Skip already processed

    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize(SIZE, Image.BILINEAR)
        img.save(output_path, format="JPEG", quality=90)
    except Exception as e:
        print(f"❌ Failed to process {image_path.name}: {e}")
