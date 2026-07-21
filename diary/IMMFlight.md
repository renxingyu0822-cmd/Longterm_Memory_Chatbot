# IMMFlight — Work Diary

## Template
**Date:** YYYY-MM-DD
**What I worked on:**
**Decisions made:**
**Blockers / questions:**
**Next steps:**

---

## 2026-07-20

**What I worked on:**

- Hardened the Flask `/chat` endpoint by validating the JSON body and message type, returning clear `400` or `502` responses, and handling retrieval, model, and memory-storage failures.
- Changed conversation-history updates so a failed or empty model response does not leave a partial user turn in history.
- Escaped stored memory text on `/memories` to prevent injected HTML or scripts from being rendered.
- Improved the browser client to prevent duplicate sends, surface server errors, validate response data, and always restore the send button and input focus.
- Added null/empty-response handling to the CLI and memory extractor.
- Added `memory.store()` for embedding and persisting one extracted memory, resolving Pylance's unknown `memory.store` attribute error in `main.py`.
- Converted Chroma embedding inputs to NumPy `float32` arrays for consistent collection operations.
- Added five Flask route tests covering malformed requests, successful chat, empty model output, conversation-history behavior, and memory-output escaping.
- Added `.venv/` and `.vscode/` to `.gitignore`.

**Decisions made:**

- Return user-safe API errors while logging detailed server exceptions.
- Treat memory extraction/storage as non-critical after a successful chat response; a memory failure should not discard the assistant response.
- Keep `store()` as an explicit public function in `memory.py` instead of dynamically probing for several possible function names, so runtime behavior and static analysis agree.
- Only commit a conversation turn to history after receiving a non-empty assistant response.

**Blockers / questions:**

- `pytest` and the Pyright CLI are not installed in the current environment. The test suite was run successfully with the standard-library `unittest` runner: 5 tests passed.

**Next steps:**

- Refresh or restart the Pylance language server if the resolved `memory.store` warning remains cached in VS Code.
- Manually exercise the chat UI with valid API credentials and verify retrieval and persistence against the local Chroma database.
- Consider consolidating the CLI extractor flow and the web app's `extract_and_store()` flow to avoid maintaining two memory-extraction paths.

---

## 2026-07-22

**What I worked on:**

- Implemented deterministic relative-date handling for episodic memories. Chinese and English expressions such as today, tomorrow, the day after tomorrow, yesterday, and their Chinese equivalents are resolved against the timezone-aware local system time.
- Added `recorded_at` and `event_date` metadata, while retaining the resolved absolute date in the memory text so its meaning does not shift on later retrieval.
- Added a fallback that always stores user messages containing relative dates as episodic memories when the extraction model returns no memory.
- Replaced the plain-text `/memories` output with a responsive long-term/short-term memory dashboard showing category counts, importance, event dates, and retention behaviour.
- Added `/memories?demo=1` with clearly labelled sample data. The demo does not write anything to Chroma.
- Expanded the unit suite to 10 passing tests, including relative-date conversion, temporal-memory fallback, demo rendering, and output escaping.
- Diagnosed the chat service's `502` response as sandboxed outbound networking rather than an invalid API key. Verified the OpenAI API independently and restarted Flask with the required network permission.
- Found and removed duplicate Flask child processes that continued listening after their parent task ended, then verified a single listener on port 8080.
- Documented short-term-to-long-term memory consolidation as the next project feature.

**Decisions made:**

- Resolve relative dates at write time using local system time, rather than interpreting words such as “tomorrow” again at retrieval time.
- Keep both memory categories in one Chroma collection and distinguish them through the `category` metadata.
- Force temporal messages into `episodic`, even if the extraction model classifies them differently or returns an empty result.
- Keep demonstration content isolated behind a query parameter so examples never contaminate real user memory.
- Treat memory consolidation as a separate planned feature with an LLM review step; access count alone should not make a temporary event permanent.

**Blockers / questions:**

- The local server needs outbound network permission to reach the OpenAI API; without it, `/chat` returns the user-safe temporary-unavailable response.
- Stopping the retained command task does not always stop its spawned Python child on Windows, so port ownership must be checked before restarting.

**Next steps:**

- Implement and evaluate `consolidate_memories()` using repeated mentions, access count, age, importance, and an LLM durability check.
- Add a reliable project start/stop helper that keeps exactly one Flask process and cleans up its child process.
- Exercise real conversations containing both stable user facts and dated plans to evaluate extraction quality and promotion thresholds.
