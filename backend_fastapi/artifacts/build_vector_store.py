import os
import json
import chromadb
from tqdm import tqdm
from typing import List, Optional
from app.core import config
from app.embeddings.titan import TitanEmbedder


# ---------------------------------------------------
# Helper: Build embedding text
# ---------------------------------------------------

def build_document_text(part: dict) -> str:
    return f"""
Part ID: {part.get('part_id')}
Title: {part.get('title')}
Brand: {part.get('brand')}
Description: {part.get('description')}
Symptoms: {", ".join(part.get('symptoms', []))}
Appliance Type: {part.get('appliance_type')}
"""


# ---------------------------------------------------
# Vector Store Class
# ---------------------------------------------------

class VectorStore:

    def __init__(self):
        self.embedder = TitanEmbedder()

        os.makedirs(config.CHROMA_DIR, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=config.CHROMA_DIR
        )

        try:
            self.collection = self.client.get_collection(
                config.CHROMA_COLLECTION
            )
        except:
            self.collection = self.client.create_collection(
                config.CHROMA_COLLECTION
            )

    # ---------------------------------------------------
    # Search (MODEL-AWARE)
    # ---------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 6,
        allowed_ids: Optional[List[str]] = None
    ):
        embedding = self.embedder.embed(query)

        # If filtering by model
        if allowed_ids and len(allowed_ids) > 0:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=k,
                where={"part_id": {"$in": allowed_ids}}
            )
        else:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=k
            )

        return results


# ---------------------------------------------------
# Build Vector Store (Run Once After Scraping)
# ---------------------------------------------------

def build_vector_store():

    print("Loading parts...")
    with open(config.PART_ID_MAP_PATH, "r") as f:
        parts = json.load(f)

    print(f"Loaded {len(parts)} parts")

    embedder = TitanEmbedder()

    os.makedirs(config.CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=config.CHROMA_DIR)

    try:
        client.delete_collection(config.CHROMA_COLLECTION)
    except:
        pass

    collection = client.create_collection(config.CHROMA_COLLECTION)

    print("Embedding and storing parts...")

    for part_id, part in tqdm(parts.items()):

        text = build_document_text(part)
        embedding = embedder.embed(text)

        metadata = {
            "part_id": part_id,
            "brand": part.get("brand") or "",
            "appliance_type": part.get("appliance_type") or ""
        }
        collection.add(
            ids=[part_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata]
        )

print("Vector store built successfully.")


# ---------------------------------------------------
# Script Entry
# ---------------------------------------------------

if __name__ == "__main__":
    build_vector_store()

# python -m artifacts.build_vector_store
