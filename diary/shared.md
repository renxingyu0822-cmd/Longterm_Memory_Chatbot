# Shared Notes

Use this file for joint decisions, meeting notes, and anything both contributors should see.

---

## Project Idea Summary — Long-Term Memory Conversational Agent

**Project Goal:** Build a conversational AI agent with long-term memory that continuously learns from user interactions, stores useful knowledge, and retrieves relevant memories to generate more personalized and context-aware responses over time.

### 8-Component Architecture

**1. Conversation Processing**
- After each conversation (or every few turns), analyze the dialogue.
- Extract structured information such as user facts, preferences, events, entities, and keywords.
- Convert unstructured conversations into reusable memories.

**2. Vector-Based Memory**
- Generate embeddings for extracted memories using an embedding model.
- Store embeddings in a vector database (e.g., Qdrant, Chroma, Milvus, or FAISS).
- Use semantic search to retrieve relevant memories during future conversations.

**3. Structured Memory Storage**
- Besides the vector database, maintain a structured database (SQL or a knowledge graph).
- Store persistent facts and relationships (e.g., user profile, interests, education, goals).
- Support precise queries in addition to semantic retrieval.

**4. Memory Retrieval**
- Embed the user's current query.
- Retrieve the most relevant memories from the vector database.
- Optionally combine semantic retrieval with structured database queries.
- Inject retrieved memories into the prompt before sending it to the LLM.

**5. Memory Importance Scoring**
- Assign each memory an importance/confidence score.
- Highly important memories (e.g., long-term goals or allergies) should be prioritized during retrieval.
- Less important memories receive lower weights.

**6. Forgetting Mechanism**
- Implement a forgetting curve or time-decay function.
- Combine importance, recency, and access frequency to determine whether memories should be retained, compressed, summarized, or removed.
- This prevents unlimited memory growth.

**7. Dynamic Memory Selection**
- Retrieve only memories relevant to the current task.
- For example, use personal preferences for casual chat, project-related memories for work discussions, and educational history for career advice.
- This keeps prompts concise and improves retrieval quality.

**8. Continuous Memory Update**
- The system continuously repeats the cycle: Conversation → Information Extraction → Memory Storage → Retrieval → Response → Memory Update.
- Over time, the agent gradually develops a persistent understanding of the user.

### Potential Future Improvements
- Conflict resolution for outdated memories (e.g., updating old information).
- Memory summarization for very long histories.
- Different memory categories (short-term vs. long-term).
- Evaluation metrics for retrieval quality and memory usefulness.
- Support for multi-user profiles.

### Overall Architecture
```
Conversation
↓
Information Extraction (Facts, Preferences, Events, Entities)
↓
Embedding + Structured Parsing
↓
Vector Database + Relational Database / Knowledge Graph
↓
Memory Scoring & Forgetting
↓
Memory Retrieval
↓
Prompt Augmentation
↓
LLM Response
```

---

## 2026-07-15 — Project Kickoff

- Repo created: https://github.com/renxingyu0822-cmd/Longterm_Memory_Chatbot
- Contributors: dafei, IMMFlight
- Project goal: conversational AI agent with persistent long-term memory
- Reviewed project summary and agreed on 8-component architecture (see README)
- Set up project folder structure: `diary/` for work diary (Obsidian), `src/` for code
- Set up Obsidian to write the shared work diary, synced via manual git

---

## 2026-07-16 — LLM + Web UI

**Tech stack decided:**
- LLM: GPT-4o-mini (OpenAI)
- Language: Python
- Web framework: Flask

**What we built:**
- Flask web app connecting the frontend to GPT-4o-mini
- Chat UI runs at http://localhost:8080

**Files in `src/`:**
- `app.py` — Flask server, handles chat requests
- `templates/index.html` — chat UI
- `requirements.txt` — openai, flask, python-dotenv

**Next steps:**
- Design and build the full memory system (SQL + vector DB + importance scoring + forgetting mechanism) following the 8-component architecture

---

## 2026-07-18 — Core Memory System (Components 1, 2, 4)

**Decisions made:**
- Vector DB: Chroma (local, file-based, no server needed — `pip install chromadb`)
- Embedding model: text-embedding-3-small (OpenAI)
- Start with vector DB directly rather than SQLite — gives semantic retrieval from day one
- Memory persists to `src/chroma_db/` on disk, survives server restarts

**What we built:**
- `src/memory.py` — new module with two functions:
  - `extract_and_store(user_msg, assistant_msg)` — calls GPT-4o-mini to extract facts from each exchange, embeds with text-embedding-3-small, stores in Chroma
  - `retrieve(query)` — embeds the user query, returns top 5 semantically similar memories
- Updated `src/app.py`:
  - Retrieves relevant memories before each LLM call, injects them into the system prompt
  - Extracts and stores new memories after each response
  - Returns `memories_saved` in the API response (displayed in UI as "💾 Remembered: ...")
  - Added `/memories` endpoint — view all stored memories at http://localhost:8080/memories

**Status:** Working end to end — chatbot remembers facts across conversations.

**Next steps:**
- Importance scoring (component 5)
- Forgetting mechanism / time-decay (component 6)
- Structured storage for precise user profile queries (component 3)

---

## 2026-07-19 — Naming, Avatar + Prompt Engineering

**What we did:**
- Named the chatbot **Thumper** — added to system prompt so it knows its own name
- Added Thumper's profile picture as a circular avatar next to every bot message and the "Thinking..." indicator
  - Image saved to `src/static/thumper.png`
  - Served via Flask's static file serving
- Rewrote the base system prompt — casual, witty, feels like chatting with someone you know well
  - No corporate filler ("Certainly!", "Of course!")
  - Weaves in memories naturally without announcing them
  - Matches the user's energy (playful vs. serious)
  - Has opinions, can push back, asks questions
- Removed the hardcoded greeting bubble — conversations now start clean

---

## 2026-07-20 — Reliability, Security + Memory Categorisation

**Security & robustness (IMMFlight):**
- Hardened the Flask `/chat` API — validates JSON body and message type, returns clear `400`/`502` errors
- Conversation history only updated after a non-empty assistant response
- Escaped memory text on `/memories` to prevent XSS
- Improved chat UI: prevents duplicate sends, surfaces server errors, validates response data
- Added 5 Flask route tests — all passing with `unittest`

**Memory system (dafei):**
- Split memories into two categories:
  - `core` — permanent facts (name, goals, preferences, personality). Never forgotten.
  - `episodic` — time-sensitive remarks (daily events, passing comments). Fade over time.
- Forgetting curve: `strength = importance × e^(−0.1 × days_since_last_access)`. Stale memories pruned on startup.
- Conflict resolution: same-topic memories (distance 0.15–0.5) replace old ones instead of duplicating.
- Deduplication: near-identical memories (distance < 0.15) are skipped.
- Updated extraction prompt to catch casual preferences (e.g. "I don't really like X").
- Thumper now starts every conversation with a greeting — introduces itself on first meeting, greets returning users by name.
- Added "Getting to know the user" to system prompt — asks for name, pronouns, interests one at a time.
- Added 🧠 Memories button in header linking to `/memories` in a new tab.
- `/memories` now shows CORE / EPISODIC sections with importance scores.

**Next steps:**
- Structured storage (SQL) for precise profile queries (component 3)
- Evaluate memory quality over longer conversations

---

## 2026-07-22 — Relative-Time Memory + Memory Dashboard

**Memory changes:**
- Episodic memories now resolve relative dates against the timezone-aware local system time at write time.
- Supported expressions include today, tomorrow, the day after tomorrow, yesterday, and their common Chinese equivalents.
- Resolved dates are retained in memory text; episodic metadata now records `recorded_at` and, when available, `event_date`.
- Messages containing relative dates are forced to `episodic` and have a deterministic storage fallback if the extraction model returns no result.
- Existing `core`/`episodic` storage, decay, retrieval scoring, deduplication, and conflict handling remain in place.

**Memory dashboard:**
- Rebuilt `/memories` as a responsive dashboard with separate long-term and short-term sections.
- Cards display importance plus either permanent-retention status or an episodic event date.
- Added `/memories?demo=1` to show both categories using clearly labelled, non-persistent example data.
- Jinja auto-escaping continues to protect rendered memory content.

**Verification:**
- Expanded the `unittest` suite from 5 to 10 tests.
- Added coverage for relative-date conversion, temporal fallback storage, metadata, demo rendering, and memory-output escaping.
- All 10 tests pass.

---

## 2026-07-22 — Next Plan: Short-Term to Long-Term Consolidation

**Status:** Planned, not implemented.

**Goal:** Allow stable and repeatedly useful `episodic` memories to become permanent `core` memories instead of only decaying or being deleted.

**Proposed design:**
- Add `consolidate_memories()` to scan short-term memories periodically.
- Select candidates using repeated mentions, `access_count`, memory age, and importance (initial proposal: at least 3 accesses/mentions and importance ≥ 0.7).
- Use an LLM review step to reject one-off events and confirm that a candidate is a durable fact, preference, habit, relationship, or ongoing goal.
- Check for duplicates and conflicts with existing `core` memories before promotion.
- On approval, change `category` from `episodic` to `core` and store `promoted_at` plus `promotion_reason` metadata.
- Initially run consolidation at application startup; consider a scheduled background task after evaluating cost and latency.

**Acceptance tests:**
- Repeated stable preferences are promoted.
- Temporary appointments and dated events are not promoted.
- Duplicate core memories are not created.
- Conflicting core memories follow the existing replacement policy.
- Candidates below the configured thresholds remain episodic.

---

## 2026-07-21 — Language Picker + Session Navigation

**What we built:**

- Replaced the header language switcher with a full-screen overlay that appears at the start of every new session.
  - The overlay shows Thumper's avatar, the title, and three language buttons (🇬🇧 English, 🇨🇳 中文, 🇩🇪 Deutsch).
  - Language is stored in `sessionStorage` (not `localStorage`), so it persists within the same browser tab but resets when a new session starts.
- Fixed the memories page navigation so it no longer breaks the chat:
  - Removed `target="_blank"` from the Memories button — memories now open in the same tab.
  - When the user returns via "← Back to chat", `sessionStorage` still holds both the language and the full chat log, so the conversation is restored exactly as left.
- Result: users always choose a language at the start, and can freely switch between the chat and memory pages without losing context.

---

## 2026-07-22 — Buffered Messaging, Multi-Bubble Replies + Localization

**Natural chat timing:**

- Replaced the one-request-per-send browser flow with a pending-message queue stored in `sessionStorage`.
- Users can send several short messages without the send button being disabled. Messages are batched after a `0.8`-second quiet period, with a 10-second maximum wait and a maximum of 10 messages per request.
- Added input and composition-event handling so Chinese IME selection does not accidentally send a message.
- If a model response finishes while the user is typing, the response is held until the input is sent or no input event has occurred for `0.8` seconds.
- Removed the visible “Thinking...” bubble. Completed responses now appear directly at the appropriate delivery time.

**Multiple assistant bubbles:**

- Added strict JSON Schema Structured Outputs to the `gpt-4o-mini` Chat Completions request.
- The model now returns `1–10` ordered reply bubbles. It is instructed to split distinct questions or topics while keeping related sentence fragments together and avoiding repeated information.
- `/chat` returns both a backward-compatible combined `response` and an ordered `responses` array.
- The browser renders each reply as a separate bot bubble, checks the user's typing state before every bubble, and uses a short inter-bubble delay for a natural chat rhythm.
- Conversation history and memory extraction receive the complete ordered reply content joined with newlines.

**Response latency and memory persistence:**

- Moved memory extraction and embedding storage out of the blocking `/chat` path.
- Added `POST /remember`; the browser calls it after displaying the assistant response and adds the localized “Remembered” tag when storage completes.
- A slow or failed memory-storage request no longer delays or interrupts the visible reply.

**Language and settings:**

- Added a gear-only settings button beside the Memories button. Its modal supports English, Simplified Chinese, and German without clearing the active conversation.
- Language changes immediately update chat controls, accessibility labels, the memory-page link, and the system instruction used for future assistant replies.
- Localized the entire memory dashboard, including headings, navigation, empty states, retention labels, demo notices, and demo memories.
- Memory and demo links preserve the selected `lang` value; stored real-memory text remains in its original language to avoid semantic changes from display-time translation.

**Backend and validation:**

- `/chat` accepts either the legacy `message` string or a validated `messages` array of up to 10 non-empty strings.
- Added validation for structured model output, reply counts, and the new `/remember` request body.
- Preserved safe conversation-history updates: invalid, empty, or malformed model output does not add a partial turn.
- Expanded the automated suite to 18 passing `unittest` tests covering batching, strict structured-output configuration, multiple replies, invalid structured responses, asynchronous memory storage, settings markup, and three-language memory pages.

**Runtime notes:**

- Diagnosed `ERR_CONNECTION_REFUSED` as an exited Flask process and a later `500` as sandbox-blocked outbound API networking (`WinError 10013`).
- Restarted Flask with network permission and repeatedly verified `HTTP 200` responses.
- Removed stale duplicate Python listeners on port `8080` before each verified restart.
