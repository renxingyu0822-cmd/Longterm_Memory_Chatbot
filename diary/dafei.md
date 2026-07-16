# dafei — Work Diary

## Template
**Date:** YYYY-MM-DD
**What I worked on:**
**Decisions made:**
**Blockers / questions:**
**Next steps:**

---

## 2026-07-15
**What I worked on:** Project kickoff — reviewed project summary, set up repo structure and Obsidian diary.

**Decisions made:**
- Use GitHub repo for collaboration
- Obsidian Git plugin for diary sync
- Dual storage: vector DB + relational DB

**Blockers / questions:**
- Tech stack not finalized yet (LLM, vector DB choice)

**Next steps:**
- Decide on LLM backend and vector DB
- Start scaffolding the core pipeline

---

## 2026-07-16
**What I worked on:** Built the core pipeline and web UI for the chatbot.

**Decisions made:**
- LLM: GPT-4o-mini
- Vector DB: ChromaDB (local)
- Language: Python
- Web UI: Flask + browser (localhost:8080)

**How to start the chatbot:**
1. Open terminal
2. Type `chatbot` (alias set up in ~/.zshrc)
3. Open http://localhost:8080 in browser
4. Close terminal when done

**Next steps:**
- Add memory importance scoring
- Add forgetting mechanism (time decay) 