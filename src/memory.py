import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
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

Current system datetime: {current_time}
For episodic memories, resolve relative dates (for example "today", "tomorrow",
"yesterday", "\u4eca\u5929", "\u660e\u5929", "\u540e\u5929") against this datetime. Include the
resolved YYYY-MM-DD date in the memory text, while preserving any stated clock time.

Return only the JSON array, nothing else."""

_DECAY_RATE = 0.1  # episodic strength halves every ~7 days

_RELATIVE_DATE_PATTERNS = (
    (re.compile(r"\u5927\u540e\u5929(?![\uff08(]\d{4}-\d{2}-\d{2}[\uff09)])"), 3),
    (re.compile(r"\u540e\u5929(?![\uff08(]\d{4}-\d{2}-\d{2}[\uff09)])"), 2),
    (re.compile(r"\u660e\u5929(?![\uff08(]\d{4}-\d{2}-\d{2}[\uff09)])"), 1),
    (re.compile(r"\u4eca\u5929(?![\uff08(]\d{4}-\d{2}-\d{2}[\uff09)])"), 0),
    (re.compile(r"\u6628\u5929(?![\uff08(]\d{4}-\d{2}-\d{2}[\uff09)])"), -1),
    (re.compile(r"\u524d\u5929(?![\uff08(]\d{4}-\d{2}-\d{2}[\uff09)])"), -2),
    (re.compile(r"\bday after tomorrow\b(?!\s*\(\d{4}-\d{2}-\d{2}\))", re.IGNORECASE), 2),
    (re.compile(r"\btomorrow\b(?!\s*\(\d{4}-\d{2}-\d{2}\))", re.IGNORECASE), 1),
    (re.compile(r"\btoday\b(?!\s*\(\d{4}-\d{2}-\d{2}\))", re.IGNORECASE), 0),
    (re.compile(r"\byesterday\b(?!\s*\(\d{4}-\d{2}-\d{2}\))", re.IGNORECASE), -1),
)


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _local_now() -> datetime:
    """Return the system-local, timezone-aware datetime used to resolve relative dates."""
    return datetime.now().astimezone()


def resolve_relative_dates(memory_text: str, reference_time: datetime | None = None) -> tuple[str, list[str]]:
    """Freeze relative date words in a memory to dates based on the recording time."""
    reference = reference_time or _local_now()
    resolved_dates: list[str] = []
    resolved_text = memory_text

    for pattern, day_offset in _RELATIVE_DATE_PATTERNS:
        target_date = (reference + timedelta(days=day_offset)).date().isoformat()

        def add_date(match: re.Match[str]) -> str:
            resolved_dates.append(target_date)
            if match.group(0)[0].isascii():
                return f"{match.group(0)} ({target_date})"
            return f"{match.group(0)}\uff08{target_date}\uff09"

        resolved_text = pattern.sub(add_date, resolved_text)

    return resolved_text, list(dict.fromkeys(resolved_dates))


def _decay_strength(importance: float, last_accessed: float) -> float:
    days = (_now() - last_accessed) / 86400
    return importance * math.exp(-_DECAY_RATE * days)


def _as_float(val, default: float = 0.5) -> float:
    try:
        return float(val)
    except Exception:
        return default


def extract_and_store(user_message: str, assistant_message: str) -> list[str]:
    recorded_at = _local_now()
    normalized_user_message, source_relative_dates = resolve_relative_dates(
        user_message.strip(), recorded_at
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(
            user_message=user_message,
            assistant_message=assistant_message,
            current_time=recorded_at.isoformat(timespec="seconds"),
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
        items = []

    if not items and source_relative_dates:
        items = [{
            "text": f"User's time-sensitive note: {normalized_user_message}",
            "category": "episodic",
            "importance": 0.5,
        }]
    elif not items:
        return []

    has_relative_time_memory = False
    for item in items:
        text, relative_dates = resolve_relative_dates(item["text"].strip(), recorded_at)
        if not relative_dates:
            relative_dates = [date for date in source_relative_dates if date in text]
        item["text"] = text
        item["relative_dates"] = relative_dates
        if relative_dates:
            item["category"] = "episodic"
            has_relative_time_memory = True

    if source_relative_dates and not has_relative_time_memory:
        items.append({
            "text": f"User's time-sensitive note: {normalized_user_message}",
            "category": "episodic",
            "importance": 0.5,
            "relative_dates": source_relative_dates,
        })

    texts = [i["text"] for i in items]
    now = recorded_at.timestamp()

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
            # Safely extract distance and id values; the Chroma client may return None or empty lists
            distances = hit.get("distances") or []
            first_dist_list = distances[0] if distances else None
            dist = float(first_dist_list[0]) if first_dist_list and len(first_dist_list) > 0 else 1.0

            if dist < 0.15:
                continue  # near-identical, skip
            if dist < 0.5:
                # same topic, different value — delete old and store new
                ids = hit.get("ids") or []
                first_id_list = ids[0] if ids else None
                old_id = first_id_list[0] if first_id_list and len(first_id_list) > 0 else None
                if old_id:
                    collection.delete(ids=[old_id])
        new_texts.append(text)
        new_embeddings.append(emb)
        metadata = {
            "category": item.get("category", "episodic"),
            "importance": float(item.get("importance", 0.5)),
            "created_at": now,
            "last_accessed": now,
            "access_count": 0,
        }
        if metadata["category"] == "episodic":
            metadata["recorded_at"] = recorded_at.isoformat(timespec="seconds")
            relative_dates = item.get("relative_dates") or []
            if relative_dates:
                metadata["event_date"] = relative_dates[0]
        new_metas.append(metadata)

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
    recorded_at = _local_now()
    relative_dates: list[str] = []
    if category == "episodic":
        text, relative_dates = resolve_relative_dates(text, recorded_at)
    now = recorded_at.timestamp()
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
            **({"recorded_at": recorded_at.isoformat(timespec="seconds")} if category == "episodic" else {}),
            **({"event_date": relative_dates[0]} if relative_dates else {}),
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

    # The chroma client may return None for any of these keys; handle safely.
    docs_list = results.get("documents") or []
    distances_list = results.get("distances") or []
    metadatas_list = results.get("metadatas") or []
    ids_list = results.get("ids") or []

    if not docs_list:
        return []

    docs = docs_list[0] if docs_list and len(docs_list) > 0 and docs_list[0] is not None else []
    distances = distances_list[0] if distances_list and len(distances_list) > 0 and distances_list[0] is not None else []
    metadatas = metadatas_list[0] if metadatas_list and len(metadatas_list) > 0 and metadatas_list[0] is not None else []
    ids = ids_list[0] if ids_list and len(ids_list) > 0 and ids_list[0] is not None else []

    now = _now()
    scored = []
    for doc, dist, meta, mem_id in zip(docs, distances, metadatas, ids):
        semantic_score = 1 / (1 + dist)
        meta = meta or {}
        if meta.get("category") == "core":
            final_score = semantic_score
        else:
            strength = _decay_strength(
                _as_float(meta.get("importance", 0.5)),
                _as_float(meta.get("last_accessed", now), default=now),
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

    ids = all_results.get("ids") or []
    metas = all_results.get("metadatas") or []

    for mem_id, meta in zip(ids, metas):
        if not meta or meta.get("category") == "core":
            continue
        strength = _decay_strength(
            _as_float(meta.get("importance", 0.5)),
            _as_float(meta.get("last_accessed", now), default=now),
        )
        if strength < threshold:
            to_delete.append(mem_id)

    if to_delete:
        collection.delete(ids=to_delete)

    return len(to_delete)
