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
