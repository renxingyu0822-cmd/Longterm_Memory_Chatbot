import json
import uuid
from pathlib import Path

import chromadb
from openai import OpenAI

client = OpenAI()

_chroma = chromadb.PersistentClient(path=str(Path(__file__).parent / "chroma_db"))
collection = _chroma.get_or_create_collection("memories")

_EXTRACT_PROMPT = """You are a memory extraction assistant. Given a conversation exchange, extract facts worth remembering about the user — personal details, preferences, goals, interests, or important events.

Return a JSON array of short, self-contained memory strings. If nothing worth remembering was said, return [].

Examples:
- "User's name is Alex"
- "User prefers Python over JavaScript"
- "User is studying for a PhD in biology"

Conversation:
User: {user_message}
Assistant: {assistant_message}

Return only the JSON array, nothing else."""


def extract_and_store(user_message: str, assistant_message: str) -> list[str]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(
            user_message=user_message,
            assistant_message=assistant_message,
        )}],
    )
    try:
        memories = json.loads(response.choices[0].message.content.strip())
        memories = [m for m in memories if isinstance(m, str) and m.strip()]
    except (json.JSONDecodeError, AttributeError):
        return []

    if not memories:
        return []

    embeddings_response = client.embeddings.create(
        model="text-embedding-3-small",
        input=memories,
    )
    embeddings = [r.embedding for r in embeddings_response.data]
    collection.add(
        documents=memories,
        embeddings=embeddings,
        ids=[str(uuid.uuid4()) for _ in memories],
    )
    return memories


def retrieve(query: str, n: int = 5) -> list[str]:
    if collection.count() == 0:
        return []
    embedding_response = client.embeddings.create(
        model="text-embedding-3-small",
        input=[query],
    )
    results = collection.query(
        query_embeddings=[embedding_response.data[0].embedding],
        n_results=min(n, collection.count()),
    )
    return results["documents"][0] if results["documents"] else []
