# Long-Term Memory Chatbot

A conversational AI agent with long-term memory that continuously learns from user interactions, stores knowledge, and retrieves relevant memories to generate personalized, context-aware responses over time.

## Project Structure

```
├── diary/          # Work diary (open in Obsidian)
│   ├── dafei.md
│   ├── IMMFlight.md
│   └── shared.md
├── notes/          # Shared project notes
└── src/            # Source code (coming soon)
```

## Diary Setup (Obsidian)

1. Open this repo folder as an Obsidian vault
2. Install the [Obsidian Git](https://github.com/denolehov/obsidian-git) community plugin
3. Configure auto-pull/push interval (recommended: 5 minutes)
4. Each contributor writes to their own diary file; use `shared.md` for joint entries

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
