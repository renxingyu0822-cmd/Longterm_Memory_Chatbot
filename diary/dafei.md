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
- Set up project folder structure: `diary/` for diary, `src/` for code

**Blockers / questions:**
- Tech stack not finalized yet

**Next steps:**
- Decide on LLM backend
- Start building the web UI

---

## 2026-07-16
**What I worked on:** Connected GPT-4o-mini to a Flask web app with a chat UI.

**Decisions made:**
- LLM: GPT-4o-mini
- Language: Python
- Web framework: Flask

**How to start the chatbot:**
1. Open terminal
2. Type `chatbot`
3. Open http://localhost:8080 in browser
4. Close terminal when done

**Next steps:**
- Build the full memory system following the 8-component architecture

---

## 2026-07-19
**What I worked on:** Prompt engineering and UI cleanup.

**How to check the memory base:**
1. Start the chatbot (`chatbot` in terminal)
2. Open http://localhost:8080/memories in browser
3. All stored memories are listed — one per line, numbered
4. If no memories have been saved yet, it shows "No memories stored yet."

**Note:** Memories are stored in `src/chroma_db/` and persist across server restarts.
