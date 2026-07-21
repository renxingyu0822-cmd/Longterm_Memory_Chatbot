# Thumper — Long-Term Memory Chatbot

A conversational AI agent with long-term memory that continuously learns from user interactions, stores knowledge, and retrieves relevant memories to generate personalized, context-aware responses over time.

## Current Status

**Phase 2 complete:** Core memory system fully working with categorisation, forgetting, and conflict resolution.
- Thumper greets users on every session — introduces itself to new users, welcomes back returning ones by name.
- Memories are split into `core` (permanent) and `episodic` (time-decay) categories.
- Conflicting memories (e.g. name changes) are automatically updated.
- Next: memory consolidation — promote stable, repeatedly useful `episodic` memories to `core`.

## Tech Stack

- **LLM:** GPT-4o-mini (OpenAI)
- **Embeddings:** text-embedding-3-small (OpenAI)
- **Vector DB:** Chroma (local, persistent)
- **Backend:** Python + Flask
- **Frontend:** HTML/CSS/JS (served by Flask)

## Project Structure

```
├── diary/                  # Work diary (open in Obsidian)
│   ├── dafei.md
│   ├── IMMFlight.md
│   └── shared.md
├── tests/                  # Unit tests
│   └── test_app.py
└── src/                    # Source code
    ├── app.py              # Flask web server
    ├── memory.py           # Memory extraction, storage, retrieval, and forgetting
    ├── requirements.txt
    ├── chroma_db/          # Persistent vector database (auto-created, git-ignored)
    ├── static/
    │   └── thumper.png     # Chatbot avatar
    └── templates/
        └── index.html      # Chat UI
```

## Getting Started

```bash
# 1. Clone the repo
git clone https://github.com/renxingyu0822-cmd/Longterm_Memory_Chatbot.git
cd Longterm_Memory_Chatbot

# 2. Install dependencies
pip3 install -r src/requirements.txt

# 3. Add your OpenAI API key
cp src/.env.example src/.env
# edit src/.env and paste your key

# 4. Run the web app
cd src
python3 app.py
```

Then open **http://localhost:8080** in your browser.

To inspect stored memories, open **http://localhost:8080/memories**.

## How Memory Works

1. **Greeting** — on page load, Thumper generates an opening message. First visit: introduces itself and asks your name. Return visits: greets you like a friend.
2. **Retrieval** — on each message, Thumper embeds the query and fetches the top 5 semantically relevant memories, injecting them into the system prompt.
3. **Extraction** — after each response, GPT-4o-mini extracts new facts and classifies them as `core` or `episodic`.
4. **Conflict resolution** — if a new memory is on the same topic as an existing one, the old one is replaced automatically.
5. **Forgetting** — episodic memories decay over time using `strength = importance × e^(−0.1 × days_since_last_access)`. Stale memories are pruned on startup.
6. **Persistence** — all memories are saved to `src/chroma_db/` and survive server restarts.

## Memory Categories

| Category | Examples | Behaviour |
|----------|----------|-----------|
| `core` | Name, goals, preferences, personality | Never forgotten |
| `episodic` | Daily events, passing remarks | Decays over ~7 days |

## Next Step — Memory Consolidation

The next planned feature is automatic promotion from short-term memory to long-term memory. It is **planned, not implemented yet**.

Initial design:

1. Periodically scan `episodic` memories as promotion candidates.
2. Use evidence such as repeated mentions, `access_count`, age, and importance. Initial thresholds will start around three accesses or mentions and importance of at least `0.7`, then be tuned through evaluation.
3. Ask the LLM to verify that a candidate represents a stable fact, preference, habit, relationship, or ongoing goal rather than a one-off event.
4. Run duplicate and conflict checks against existing `core` memories.
5. Promote approved memories by changing their category to `core` and recording `promoted_at` and `promotion_reason` metadata.
6. Add tests covering successful promotion, rejected temporary events, duplicates, conflicts, and threshold boundaries.

Planned API: `consolidate_memories()` in `src/memory.py`, run on startup initially and later moved to a scheduled background task if needed.

## Planned Architecture

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

## Diary Setup (Obsidian)

1. Clone the repo and open the `diary/` folder as an Obsidian vault
2. Each contributor writes to their own diary file; use `shared.md` for joint entries
3. Sync manually via terminal:
   ```bash
   git pull
   git add diary/
   git commit -m "diary: update"
   git push
   ```
