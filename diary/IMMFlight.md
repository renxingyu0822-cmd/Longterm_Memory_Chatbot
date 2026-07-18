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
