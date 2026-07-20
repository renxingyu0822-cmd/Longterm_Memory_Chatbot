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

## 2026-07-20 — Reliability, Security + Memory Storage Fixes

**What changed:**

- Hardened the Flask `/chat` API:
  - Validates that the request body is a JSON object and `message` is a string.
  - Returns clear `400` responses for invalid input and `502` responses for upstream failures.
  - Handles memory retrieval, OpenAI response, and memory extraction/storage failures without crashing the route.
- Conversation history is now updated only after a non-empty assistant response, preventing incomplete turns after failed requests.
- Escaped memory text rendered by `/memories` to prevent stored HTML or JavaScript from being executed.
- Improved the chat UI:
  - Prevents duplicate submissions while a request is running.
  - Displays error messages returned by the server.
  - Validates response data and always restores the send button and input focus.
- Added safe handling for empty OpenAI responses in the CLI and standalone extractor.
- Added an explicit `memory.store(memory_text, memory_id)` API for embedding and saving individual memories. This fixes the missing `memory.store` implementation and its Pylance error in `main.py`.
- Normalized Chroma embedding inputs as NumPy `float32` arrays.
- Ignored local `.venv/` and `.vscode/` directories in Git.

**Testing:**

- Added five Flask route tests for request validation, successful chat, empty model responses, history consistency, and safe memory rendering.
- All five tests pass with Python's `unittest` runner.

**Commit:** `79e029d` — `fix: improve chat error handling and memory storage`

**Suggested next steps:**

- Test the complete chat, retrieval, and persistence flow manually with valid OpenAI credentials.
- Consolidate the CLI's separate extractor/store flow with the web app's `extract_and_store()` flow.
- Continue with importance scoring, time-based forgetting, and structured user-profile storage.
