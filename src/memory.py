import chromadb
from chromadb.utils import embedding_functions

client = chromadb.PersistentClient(path="./chroma_db")
ef = embedding_functions.DefaultEmbeddingFunction()
collection = client.get_or_create_collection("memories", embedding_function=ef)


def store(memory: str, memory_id: str) -> None:
    collection.upsert(documents=[memory], ids=[memory_id])


def retrieve(query: str, top_k: int = 5) -> list[str]:
    if collection.count() == 0:
        return []
    results = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))
    return results["documents"][0]
