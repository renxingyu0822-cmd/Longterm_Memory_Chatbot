# Thumper — Long-Term Memory Chatbot

A conversational AI agent with long-term memory that continuously learns from user interactions, stores knowledge, and retrieves relevant memories to generate personalized, context-aware responses over time.

## Current Status

**Phase 2 in progress:** Core memory system built and working.
- Thumper extracts facts from every conversation, stores them in a Chroma vector database, and retrieves relevant memories on each new message.
- Next: importance scoring, forgetting mechanism, structured storage.

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
└── src/                    # Source code
    ├── app.py              # Flask web server
    ├── memory.py           # Memory extraction, storage, and retrieval
    ├── requirements.txt
    ├── chroma_db/          # Persistent vector database (auto-created)
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

1. **Retrieval** — on each message, Thumper embeds the query and fetches the top 5 semantically relevant memories from Chroma, injecting them into the system prompt.
2. **Extraction** — after each response, GPT-4o-mini extracts any new facts worth remembering and stores them as embeddings in Chroma.
3. **Persistence** — memories are saved to `src/chroma_db/` and survive server restarts.

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
