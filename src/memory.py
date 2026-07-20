import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import numpy as np
from openai import OpenAI

client = OpenAI()

_chroma = chromadb.PersistentClient(path=str(Path(__file__).parent / "chroma_db"))
collection = _chroma.get_or_create_collection("memories")

_EXTRACT_PROMPT = """You are a memory extraction assistant. Given a conversation exchange, extract anything worth remembering about the user.

Classify each memory as:
- "core": permanent or long-lasting facts — name, age, occupation, relationships, goals, health info, personality traits, likes, dislikes, preferences. Never forgotten.
- "episodic": time-sensitive or one-off remarks — today's events, passing comments, temporary plans. Fade over time.

Also assign an importance score from 0.0 to 1.0.

Be generous — capture preferences and opinions even if stated casually (e.g. "I don't really like X" → "User dislikes X").

Return a JSON array. If nothing worth remembering was said, return [].

Example output:
[
  {{"text": "User's name is Alex", "category": "core", "importance": 0.95}},
  {{"text": "User dislikes sunshine", "category": "core", "importance": 0.7}},
  {{"text": "User had a stressful meeting today", "category": "episodic", "importance": 0.3}}
]

Conversation:
User: {user_message}
Assistant: {assistant_message}

Return only the JSON array, nothing else."""

_DECAY_RATE = 0.1  # episodic strength halves every ~7 days


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _decay_strength(importance: float, last_accessed: float) -> float:
    days = (_now() - last_accessed) / 86400
    return importance * math.exp(-_DECAY_RATE * days)


def extract_and_store(user_message: str, assistant_message: str) -> list[str]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(
            user_message=user_message,
            assistant_message=assistant_message,
        )}],
    )
    content = response.choices[0].message.content
    if not content:
        return []
    try:
        items = json.loads(content.strip())
        items = [
            i for i in items
            if isinstance(i, dict) and isinstance(i.get("text"), str) and i["text"].strip()
        ]
    except (json.JSONDecodeError, AttributeError):
        return []

    if not items:
        return []

    texts = [i["text"].strip() for i in items]
    now = _now()

    embeddings_response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    embeddings = [r.embedding for r in embeddings_response.data]

    new_texts, new_embeddings, new_metas = [], [], []
    for text, emb, item in zip(texts, embeddings, items):
        if collection.count() > 0:
            hit = collection.query(
                query_embeddings=np.array([emb], dtype=np.float32),
                n_results=1,
                include=["distances"],
            )
            dist = hit["distances"][0][0] if hit["distances"][0] else 1.0
            if dist < 0.15:
                continue  # near-identical, skip
            if dist < 0.5:
                # same topic, different value — delete old and store new
                old_id = hit["ids"][0][0]
                collection.delete(ids=[old_id])
        new_texts.append(text)
        new_embeddings.append(emb)
        new_metas.append({
            "category": item.get("category", "episodic"),
            "importance": float(item.get("importance", 0.5)),
            "created_at": now,
            "last_accessed": now,
            "access_count": 0,
        })

    if not new_texts:
        return []

    collection.add(
        documents=new_texts,
        embeddings=np.array(new_embeddings, dtype=np.float32),
        metadatas=new_metas,
        ids=[str(uuid.uuid4()) for _ in new_texts],
    )
    return new_texts


def store(memory_text: str, category: str = "core", importance: float = 0.9, memory_id: str | None = None) -> None:
    text = memory_text.strip()
    if not text:
        return
    now = _now()
    embedding_response = client.embeddings.create(
        model="text-embedding-3-small",
        input=[text],
    )
    collection.add(
        documents=[text],
        embeddings=np.array([embedding_response.data[0].embedding], dtype=np.float32),
        metadatas=[{
            "category": category,
            "importance": importance,
            "created_at": now,
            "last_accessed": now,
            "access_count": 0,
        }],
        ids=[memory_id or str(uuid.uuid4())],
    )


def retrieve(query: str, n: int = 5) -> list[str]:
    if collection.count() == 0:
        return []

    embedding_response = client.embeddings.create(
        model="text-embedding-3-small",
        input=[query],
    )
    query_emb = np.array([embedding_response.data[0].embedding], dtype=np.float32)

    n_candidates = min(n * 3, collection.count())
    results = collection.query(
        query_embeddings=query_emb,
        n_results=n_candidates,
        include=["documents", "distances", "metadatas"],
    )

    docs = results["documents"][0]
    distances = results["distances"][0]
    metadatas = results["metadatas"][0]
    ids = results["ids"][0]

    now = _now()
    scored = []
    for doc, dist, meta, mem_id in zip(docs, distances, metadatas, ids):
        semantic_score = 1 / (1 + dist)
        meta = meta or {}
        if meta.get("category") == "core":
            final_score = semantic_score
        else:
            strength = _decay_strength(
                meta.get("importance", 0.5),
                meta.get("last_accessed", now),
            )
            final_score = semantic_score * strength
        scored.append((final_score, doc, meta, mem_id))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:n]

    for _, _, meta, mem_id in top:
        collection.update(
            ids=[mem_id],
            metadatas=[{
                **meta,
                "last_accessed": now,
                "access_count": int(meta.get("access_count", 0)) + 1,
            }],
        )

    return [doc for _, doc, _, _ in top]


def forget(threshold: float = 0.05) -> int:
    """Delete episodic memories whose decay strength has fallen below threshold. Returns count deleted."""
    if collection.count() == 0:
        return 0

    all_results = collection.get(include=["metadatas"])
    now = _now()
    to_delete = []

    for mem_id, meta in zip(all_results["ids"], all_results["metadatas"]):
        if not meta or meta.get("category") == "core":
            continue
        strength = _decay_strength(
            meta.get("importance", 0.5),
            meta.get("last_accessed", now),
        )
        if strength < threshold:
            to_delete.append(mem_id)

    if to_delete:
        collection.delete(ids=to_delete)

    return len(to_delete)
