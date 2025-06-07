# api/chroma_client.py
from chromadb import PersistentClient

# Inicializa ChromaDB con almacenamiento persistente
chroma_client = PersistentClient(path="chroma_db")
collection = chroma_client.get_or_create_collection(name="cattle_brands_tf")