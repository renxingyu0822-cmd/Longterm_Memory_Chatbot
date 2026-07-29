# Project Working Instructions

## Automatic diary logging

- After every substantive user-directed project operation, append a concise dated record of the user's request, decisions, and operational outcome to the active collaborator's personal diary, resolved by the routing rules below.
- After every project change, append a concise dated record of the implementation, affected behavior, and verification results to `diary/shared.md`.
- Do not log lightweight requests that do not operate on the project, such as asking only for a title, wording, translation, or brief explanation.
- Keep related work grouped under the same dated section when practical, and do not duplicate an entry that has already been recorded.
- Never write secrets, API keys, credentials, or other sensitive values into any diary.
- Treat these diary updates as part of completing the operation; do not wait for a separate reminder.

### Collaborator identity and personal-diary routing

- Resolve the active collaborator in this priority order:
  1. An explicit identity statement from the user in the current conversation.
  2. The repository-local value from `git config --local --get codex.collaborator`.
  3. The Git identity from `git config --get user.name`.
- Match collaborator names case-insensitively and route them as follows:
  - `IMMFlight` → `diary/IMMFlight.md`
  - `dafei` → `diary/dafei.md`
- Write each user-directed operation to exactly one personal diary: never copy the same operation into both collaborators' diaries.
- Continue writing project-wide implementation and verification notes to `diary/shared.md` regardless of which collaborator is active.
- If the identity is missing, ambiguous, or does not match either collaborator, do not guess. Ask the user once, then recommend persisting the answer locally with `git config --local codex.collaborator IMMFlight` or `git config --local codex.collaborator dafei`.
- A repository-local `codex.collaborator` setting is clone-specific and must not be committed, making it suitable when `git user.name` does not exactly match the collaborator name.

### `diary/shared.md` chronology and grouping

- Keep dated sections in ascending chronological order, from oldest to newest.
- Use exactly one level-two heading per date, formatted as `## YYYY-MM-DD` with no topic suffix.
- Put separate changes made on the same date under concise level-three topic headings (`### Topic`) within that date section.
- When a date already exists, merge new material into that section instead of creating another dated heading; combine closely related implementation and verification notes and remove duplicate statements.
- When adding an older or backfilled record, insert it at the correct chronological position rather than appending it out of order.

## README synchronization

- Whenever the project structure changes, automatically review and update `README.md` as part of the same operation.
- Structure changes include adding, deleting, moving, or renaming project files or directories, as well as changing entry points, service boundaries, module responsibilities, startup commands, or documented paths.
- Keep the README's project tree, setup/run instructions, architecture descriptions, and affected file references consistent with the resulting repository state.
- Do not make a cosmetic README edit when the structural change has no user- or contributor-facing documentation impact; record that the README was reviewed and remained accurate instead.
