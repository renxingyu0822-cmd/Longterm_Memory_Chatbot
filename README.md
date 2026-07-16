# Long-Term Memory Chatbot

A conversational AI agent with long-term memory that continuously learns from user interactions, stores knowledge, and retrieves relevant memories to generate personalized, context-aware responses over time.

## Current Status

Phase 1 complete: LLM connected to a web chat UI.
Memory system (SQL + vector DB + scoring + forgetting) to be built next.

## Tech Stack

- **LLM:** GPT-4o-mini (OpenAI)
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
    ├── requirements.txt
    └── templates/
        └── index.html      # Chat UI
```

## Getting Started

```bash
# 1. Clone the repo
git clone https://github.com/renxingyu0822-cmd/Longterm_Memory_Chatbot.git
cd Longterm_Memory_Chatbot/src

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. Add your OpenAI API key
cp .env.example .env
# edit .env and paste your key

# 4. Run the web app
python3 app.py
```

Then open **http://localhost:8080** in your browser.

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
