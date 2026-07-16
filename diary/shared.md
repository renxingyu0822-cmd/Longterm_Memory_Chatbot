# Shared Notes

Use this file for joint decisions, meeting notes, and anything both contributors should see.

---

## 2026-07-15 — Project Kickoff

- Repo created: https://github.com/renxingyu0822-cmd/Longterm_Memory_Chatbot
- Contributors: dafei, IMMFlight
- Project goal: conversational AI agent with persistent long-term memory
- Reviewed project summary and agreed on 8-component architecture (see README)
- Set up project folder structure: `diary/` for work diary (Obsidian), `src/` for code
- Set up Obsidian to write the shared work diary, synced via manual git
- Tech stack not yet decided — next step is to choose LLM backend and vector DB

---

## 2026-07-16 — Core Pipeline + Web UI

**Tech stack decided:**
- LLM: GPT-4o-mini (OpenAI)
- Vector DB: ChromaDB (local, persistent)
- Language: Python

**Work pipeline:**

```
User Input
↓
Retrieve relevant memories from ChromaDB (semantic search)
↓
Inject memories into system prompt
↓
Send to GPT-4o-mini → get response
↓
Extract new facts from the conversation turn (GPT-4o-mini)
↓
Store new facts in ChromaDB
↓
(repeat)
```

**Files built today (`src/`):**
- `main.py` — conversation loop, prompt augmentation
- `extractor.py` — extracts facts/preferences from each conversation turn
- `memory.py` — ChromaDB wrapper for storing and retrieving memories
- `requirements.txt` — openai, chromadb, python-dotenv

**Next steps:**
- Add memory importance scoring
- Add forgetting mechanism (time decay)
- Test end-to-end with real conversations

**Web UI:**
- Built with Flask, runs at http://localhost:8080
- Shows what memories were saved after each message
- Start with `chatbot` command in terminal
