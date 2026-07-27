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
- Proposed and iteratively refined a social-app-style conversation flow in which several short user messages can be sent before Thumper replies.
- Chose a `0.8`-second quiet window after testing shorter timings, while keeping a 10-second maximum batch wait and a 10-message batch limit.
- Requested that generated replies remain hidden while the user is actively typing and appear as soon as the input pauses or is sent.
- Requested support for multiple assistant chat bubbles rather than forcing every batch into one large response; expanded the requested limit from two or three bubbles to as many as ten.
- Requested faster perceived replies, leading to memory extraction and vector storage being moved out of the blocking chat-response path.
- Refined the interface by removing the visible “Thinking...” indicator, adding a settings dialog, and simplifying its trigger to a gear-only icon.
- Required English, Chinese, and German selections to stay consistent across the chat interface, assistant replies, settings dialog, and memory dashboard.
- Started and exercised the local Flask application repeatedly, reported the browser's `ERR_CONNECTION_REFUSED` screenshot, and helped verify the corrected runtime behaviour.
- Asked for today's work and code changes to be recorded in the personal and shared diaries.

**Decisions made:**

- Resolve relative dates at write time using local system time, rather than interpreting words such as “tomorrow” again at retrieval time.
- Keep both memory categories in one Chroma collection and distinguish them through the `category` metadata.
- Force temporal messages into `episodic`, even if the extraction model classifies them differently or returns an empty result.
- Keep demonstration content isolated behind a query parameter so examples never contaminate real user memory.
- Treat memory consolidation as a separate planned feature with an LLM review step; access count alone should not make a temporary event permanent.
- Preserve the natural short-message buffer rather than replying immediately to every sentence.
- Treat separate questions as separate reply bubbles while allowing fragments about the same topic to remain grouped.
- Generate replies while the user types, but defer their visual delivery until the user pauses for `0.8` seconds or clears the input by sending.
- Keep memory persistence asynchronous so it cannot delay the visible assistant reply.
- Keep the settings button visually minimal while retaining localized tooltips and accessibility labels.

**Blockers / questions:**

- The local server needs outbound network permission to reach the OpenAI API; without it, `/chat` returns the user-safe temporary-unavailable response.
- Stopping the retained command task does not always stop its spawned Python child on Windows, so port ownership must be checked before restarting.

**Next steps:**

- Implement and evaluate `consolidate_memories()` using repeated mentions, access count, age, importance, and an LLM durability check.
- Add a reliable project start/stop helper that keeps exactly one Flask process and cleans up its child process.
- Exercise real conversations containing both stable user facts and dated plans to evaluate extraction quality and promotion thresholds.
- Test real conversations with several rapidly entered questions and confirm the model chooses sensible bubble boundaries from one to ten replies.
- Evaluate whether the `0.8`-second pause feels natural across desktop, mobile, and Chinese IME input.

---

## 2026-07-26 — Investment Workspace and Commit Preparation

**What I worked on:**

- Added a local investment workspace to Thumper and linked it from the chat and memory pages.
- Split assets into stocks and funds, with dedicated views for A-shares, Hong Kong stocks, U.S. stocks, exchange-traded funds, and OTC funds.
- Added independent watchlist and portfolio flows, plus immutable buy, sell, subscription, redemption, dividend, and fee records.
- Implemented SQLite-backed position accounting for weighted-average cost, realized and unrealized profit, dividends, and total return.
- Added a replaceable market-data layer that uses Yahoo Finance on a best-effort basis and falls back to clearly labelled deterministic demo data.
- Added 1-, 3-, 5-, and 20-trading-day trend probabilities, risk metrics, walk-forward backtests, and a cost-aware strategy simulation.
- Added asset search, portfolio summaries, transaction entry, asset-detail charts, Server-Sent Events, and a background refresh tracker.
- Documented the investment workspace, runtime configuration, data-source limitations, and investment-risk disclaimer.
- Added market database, prediction, service, and route tests, and fixed safe JSON delivery of the localized memory-deletion confirmation text.
- Ran the focused market test suite successfully: all 8 tests passed.
- Reviewed the staged changes before committing. The first Git commit was cancelled because its message was empty, so I generated the English title `feat: add an investment tracking workspace with market predictions` for the retry.
- Asked to open the current Codex diff and clarified that this meant the change-review view rather than a file named `codex.diff`.
- Requested that Codex diff review work normally in VS Code.

**Decisions made:**

- Keep watchlist membership independent from ownership so an asset can be followed without being held.
- Recalculate positions from the immutable transaction ledger instead of storing editable position totals.
- Isolate the market-data provider so the prototype source can be replaced by a licensed provider before public release.
- Label fallback data as demo data and treat OTC fund values as delayed official NAVs rather than real-time prices.
- Present predictions and simulations as experimental research output, not investment advice.
- Prefer reviewing code changes through the Codex diff review experience in VS Code.

**Blockers / questions:**

- The initial commit did not proceed because no commit message was supplied; the staged changes were preserved.
- Yahoo Finance is only a prototype data source and may be delayed or unavailable. A licensed feed and redistribution review are still required for public use.

**Next steps:**

- Retry the commit with the prepared English title.
- Replace the prototype feed with a licensed provider before public deployment.
- Exercise the workspace with real portfolio data and expand accounting and market-provider edge-case coverage.

---

## 2026-07-26 — Portfolio Import and Investment UX Follow-up

**What I worked on:**

- Requested one-click portfolio import from screenshots and common document, text, and spreadsheet formats.
- Chose separate import actions for current holdings and watchlist-only assets, and required every imported or newly purchased holding to appear in the watchlist automatically.
- Asked for imported holdings to use quantity or fund shares plus average cost, while watchlist imports should work with only an asset code or name.
- Requested more accurate OTC-fund behaviour: official delayed NAV data, fund-specific labels and transaction types, and no invented stock-like demo price for an unknown fund.
- Asked for the investment workspace to remember the selected asset class, market tab, list view, and an unfinished transaction form when navigating away or reloading the page.
- Requested clearer feedback when the running local server is stale and does not yet expose the new import endpoint.
- Asked for the README to be reorganized into a complete guide covering setup, configuration, imports, architecture, tests, data scope, and investment limitations.
- Asked for my actions to be recorded in `IMMFlight.md` and the corresponding project changes to be recorded in `shared.md`.

**Decisions made:**

- Treat a holdings import as an opening buy or subscription at the supplied average cost, not as a reconstruction of the account's full historical trade ledger.
- Allow partial import success so one unmatched or malformed row does not discard valid rows from the same file.
- Match imported assets against the active data provider and reject ambiguous matches instead of guessing.
- Keep navigation state and unfinished transaction drafts session-scoped in the browser.
- Prefer published OTC-fund NAVs and retain the latest official value if a refresh fails.

**Blockers / questions:**

- Screenshot and rich-document imports require a configured OpenAI API key and network access; locally structured formats can be parsed without the model.
- Yahoo Finance and Eastmoney remain prototype public sources whose availability and redistribution terms are not suitable for an unsupported public deployment.
- The 24 focused market/import tests pass. Full discovery currently has 7 failures and 1 error among 42 tests in the separate chat/memory suite, caused by unintended live OpenAI calls and an outdated XSS assertion that rejects the page's own legitimate script tags.

**Next steps:**

- Exercise imports using representative broker screenshots and exports, especially ambiguous names, duplicate rows, multiple share classes, and partially invalid files.
- Verify session recovery and transaction drafts across refreshes and navigation on both desktop and mobile browsers.
- Replace prototype market sources with licensed providers before any public release.

---

## 2026-07-26 — OTC Fund Prediction Semantics and Automatic Diary Logging

**What I worked on:**

- Clarified that the prediction change applies specifically to OTC funds rather than stocks or exchange-traded funds.
- Required all 1-, 3-, 5-, and 20-trading-day OTC-fund predictions to compare the official NAV at the end of the forecast period with the official NAV at its start.
- Required every OTC-fund horizon to show only `up` or `down`, with no neutral/flat outcome.
- Asked Codex to start the local project, verify the chat and investment pages, and keep only one Flask listener on port `8080`.
- Instructed Codex to automatically record future user operations in `diary/IMMFlight.md` and project changes in `diary/shared.md`.

**Decisions made:**

- Preserve all four forecast horizons for OTC funds while making each horizon binary.
- Exclude unchanged-NAV observations from binary backtest accuracy instead of forcing them into either direction.
- Persist the automatic diary rule in the repository-level `AGENTS.md` so it applies in future project sessions.
- Limit automatic logging to substantive project operations; title-only and similar lightweight requests are not recorded.
- Keep secrets and credentials out of both diary files.

**Operational outcome:**

- The updated investment behavior passed all 20 focused market tests, along with Python compilation and frontend JavaScript syntax checks.
- The project was started at `http://127.0.0.1:8080`; duplicate old Flask processes were removed and one verified listener was retained.

---

## 2026-07-27 — OTC Fund NAV Refresh Diagnosis

**What I worked on:**

- Investigated why OTC-fund NAVs, daily changes, and portfolio returns had not updated by the evening.
- Checked whether the tracked-asset count contained an unexpected extra item.

**Operational outcome:**

- Confirmed the background tracker and manual refresh endpoint were running normally; refreshed quotes were received at about 22:08 China time.
- Confirmed all tracked domestic OTC funds still returned an official NAV dated 2026-07-24 from Eastmoney, while the tracked QDII fund remained dated 2026-07-23.
- Determined that the unchanged UI values came from the upstream official NAV dates rather than frontend caching or a failed scheduler. No application code was changed.
- Confirmed that `600519 贵州茅台` was added directly to the watchlist at 16:46 China time on 2026-07-26 without a transaction, increasing the tracked count from 14 to 15; it was not removed during diagnosis.

---

## 2026-07-27 — Investment-Habit Memory Status Check

**What I worked on:**

- Checked whether watchlist changes, portfolio imports, and investment transactions automatically produce long-term memories about investment habits or preferences.

**Operational outcome:**

- Confirmed that automatic memory extraction currently runs only for chat exchanges; investment actions persist in the separate SQLite investment store without invoking the Chroma memory pipeline.
- Confirmed that the current long-term memory collection contains no investment-preference entries, and the unused `investment_notes` table is empty.
- No application code or investment data was changed.

---

## 2026-07-27 — Automatic Investment-Habit Memory

**What I worked on:**

- Asked Codex to implement automatic recording of investment habits from watchlist, portfolio, transaction, and import activity.

**Decisions made:**

- Record only explainable patterns supported by current activity, such as dominant asset type, repeated theme interest, or maintaining a broad observation list.
- Do not infer risk tolerance, financial capacity, trading skill, or durable trading style from sparse data.
- Keep generated habits dismissible; a dismissed habit stays hidden until its supporting evidence changes.

**Operational outcome:**

- Investment actions now recompute and persist structured habits in SQLite, expose them through the market dashboard, show them as long-term memories, and inject them into chat context.
- Existing data produced four active records: holdings primarily in OTC funds, tracked assets primarily in OTC funds, broad watchlist use before holding, and repeated technology-theme interest.
- The focused 27-test verification set passed, including all 23 market tests and new chat/memory integration tests. Full chat tests remained at the known baseline of 7 failures and 1 error.
- Restarted the local service and verified one listener at `http://127.0.0.1:8080`, a dashboard count of four investment habits, and successful rendering on the memory page.

---

## 2026-07-27 — Daily Official Fund NAV Refresh Fix

**What I worked on:**

- Investigated why official OTC-fund NAVs, daily changes, and portfolio returns still had not advanced after 23:00.
- Required the application to continue refreshing official fund data automatically every day.

**Decisions made:**

- Use Eastmoney's official NAV-history response for the latest quote instead of the slower fund-search metadata.
- Keep a short cache and check every background refresh cycle while the local service is running.
- Merge the long trend series with recent official NAV rows so the latest published date also appears in asset history.

**Operational outcome:**

- Confirmed the old search metadata still reported 2026-07-24 while the official endpoint already reported 2026-07-27.
- Updated current positions to `026789` NAV `0.8472` (`+2.05%`) and `022364` NAV `5.3757` (`+4.01%`), with portfolio returns recalculated automatically.
- Most tracked domestic funds now show 2026-07-27 in both the latest quote and history. `027898` remains at the upstream official date 2026-07-24, and the QDII fund `012920` remains at 2026-07-24 according to its delayed publication schedule.
- Added regression coverage for stale search metadata, fresh official NAVs, cache invalidation, and automatic daily history advancement; all 24 market tests passed.
- Restarted one network-enabled Flask listener on port `8080` and verified the background tracker continues independently of an open browser page.
