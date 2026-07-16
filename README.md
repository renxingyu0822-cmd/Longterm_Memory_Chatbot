# Long-Term Memory Chatbot

A conversational AI agent with long-term memory that continuously learns from user interactions, stores knowledge, and retrieves relevant memories to generate personalized, context-aware responses over time.

## Tech Stack

- **LLM:** GPT-4o-mini (OpenAI)
- **Vector DB:** ChromaDB (local, persistent)
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
    ├── main.py             # CLI version
    ├── extractor.py        # Extracts facts from conversations
    ├── memory.py           # ChromaDB store & retrieve
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

1. Clone the repo: `git clone https://github.com/renxingyu0822-cmd/Longterm_Memory_Chatbot.git`
2. Open the `diary/` folder as an Obsidian vault
3. Each contributor writes to their own diary file; use `shared.md` for joint entries
4. Sync manually via terminal:
   ```bash
   git pull                          # get latest from your collaborator
   git add diary/
   git commit -m "diary: update"
   git push
   ```

## Architecture Overview

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
