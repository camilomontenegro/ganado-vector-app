import os
import requests
from duckduckgo_search import DDGS
from pathlib import Path
from tqdm import tqdm

# Search parameters
QUERY = "cattle iron brands"
MAX_IMAGES = 30
OUTPUT_FOLDER = Path("images")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# Start search
with DDGS() as ddgs:
    results = ddgs.images(keywords=QUERY, max_results=MAX_IMAGES)

    for item in tqdm(results, total=MAX_IMAGES):
        url = item.get("image")
        if not url:
            continue

        filename = os.path.basename(url.split("?")[0])
        filepath = OUTPUT_FOLDER / filename

        if filepath.exists():
            continue

        try:
            response = requests.get(url, timeout=10)
            with open(filepath, "wb") as f:
                f.write(response.content)
        except Exception as e:
            print(f"⚠️ Could not download {url}: {e}")
