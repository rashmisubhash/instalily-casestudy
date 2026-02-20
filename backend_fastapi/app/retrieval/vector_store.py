import chromadb
from app.core import config
from app.embeddings.titan import TitanEmbedder


class VectorStore:

    def __init__(self):
        self.client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        self.collection = self.client.get_collection(config.CHROMA_COLLECTION)
        self.embedder = TitanEmbedder()

    def search(self, query: str, k: int = 5):
        embedding = self.embedder.embed(query)

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=k
        )

        return results
