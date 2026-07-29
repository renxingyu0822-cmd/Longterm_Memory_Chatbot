# Thumper — Long-Term Memory Chatbot

Thumper is a local-first conversational companion with persistent long-term memory and an optional personal investment research workspace. It combines an OpenAI-powered chat experience and Chroma-based memory retrieval in a Flask chatbot, with a separately runnable investment service that the chatbot can query as a tool when needed.

> The investment features are experimental research tools. They are not investment advice, trading signals, or promises of future performance.

## Current Features

### Conversation and memory

- Natural multi-message chat with an always-available send control: messages render immediately, enter a sequential background queue, share an 800 ms batch when sent close together, and merge after a silent `WAIT` when the user appears to be mid-thought.
- Deterministic reply timing: after the model responds, the UI waits for the user to be idle before displaying the reply, without dropping messages sent during processing.
- Ready replies are inserted directly with no “Typing…” placeholder or simulated per-bubble typing delay.
- English, Simplified Chinese, and German chat modes, switchable during a conversation.
- Automatic extraction of durable facts and recent events with `gpt-4o-mini`.
- Explainable investment-habit memories derived from watchlist and portfolio actions without guessing risk tolerance from sparse data.
- Semantic retrieval with `text-embedding-3-small` and a local persistent Chroma collection.
- Two memory categories: permanent `core` memories and decaying `episodic` memories.
- Relative dates such as “tomorrow” and “明天” are resolved to a concrete date when the memory is recorded.
- A memory dashboard with demo data, importance display, and manual deletion.

### Investment workspace

Open `http://localhost:8081/market`, or select **Investments / 投资** in the chat header.

- Separate views for A-shares, Hong Kong stocks, U.S. stocks, exchange-traded funds, and OTC funds.
- Portfolio and watchlist-only views. Every held asset is also included in the watchlist.
- Search by symbol or name, then add an asset to the watchlist or record a position.
- Immutable buy, sell, subscription, redemption, dividend, and fee records.
- Automatic weighted-average cost, realized profit, unrealized profit, dividends, fees, and total-return calculations.
- One-click portfolio or watchlist import from screenshots, PDF/Word documents, CSV/TSV/TXT/JSON, and XLS/XLSX files.
- Experimental 1, 3, 5, and 20 trading-day probabilities: stocks and exchange-traded funds use up / flat / down, while OTC funds use only up / down and compare the official NAV at the end of each horizon with the official NAV at its start.
- Asset detail pages with price history, risk metrics, and walk-forward backtests, plus a cost-aware probability-threshold simulation for stocks and exchange-traded funds.
- Background refresh while the local server is running, plus Server-Sent Events for dashboard updates.

The default `hybrid` provider uses Yahoo Finance on a best-effort basis for exchange-traded assets and Eastmoney for OTC fund search and official NAV history. OTC quotes are read from Eastmoney's official NAV-history response rather than its slower search metadata, and the background tracker checks for a newly published NAV every refresh cycle while the server is running. If a network request or supported symbol is unavailable, the application may fall back to clearly labelled deterministic demo data. These sources are suitable for local prototyping only; use a licensed provider and review redistribution terms before any public release.

OTC funds do not have exchange-traded real-time prices. Their latest officially published NAV is treated as delayed data. An unknown OTC fund is never assigned a stock-like simulated intraday price.

## Tech Stack

- **Backend:** Python 3.10+ and Flask
- **Chat and memory extraction:** `gpt-4o-mini`
- **Embeddings:** `text-embedding-3-small`
- **Memory store:** Chroma, persisted locally
- **Investment store:** SQLite
- **Market data:** replaceable hybrid provider (Yahoo Finance, Eastmoney, and labelled demo fallback)
- **Frontend:** server-rendered HTML with vanilla CSS and JavaScript

## Getting Started

### 1. Clone and enter the project

```bash
git clone https://github.com/renxingyu0822-cmd/Longterm_Memory_Chatbot.git
cd Longterm_Memory_Chatbot
```

### 2. Create an environment and install dependencies

```bash
python -m venv .venv
python -m pip install -r src/requirements.txt
```

Activate the virtual environment using the command for your shell if needed. For PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Configure the application

Copy the example environment file and add your OpenAI API key:

```bash
cp src/.env.example src/.env
```

On PowerShell:

```powershell
Copy-Item src/.env.example src/.env
```

At minimum, set:

```dotenv
OPENAI_API_KEY=your_api_key_here
```

The API key is required for chat, embeddings, memory extraction, and image/rich-document portfolio imports. Delimited text, JSON, and XLSX imports are parsed locally.

### 4. Run the chatbot

```bash
cd src/chatbot
python app.py
```

Then open:

- Chat: `http://localhost:8080`
- Memories: `http://localhost:8080/memories`

Chat conversation history is kept in process memory and clears on restart; extracted memories persist in `src/chroma_db/`.

### 5. Run the investment service (optional)

The investment workspace is a separate process. Start it in a second terminal if you want portfolio and market features:

```bash
cd src/investment
python investment_app.py
```

Then open `http://localhost:8081/market`.

The background market tracker starts with the investment service and refreshes tracked assets while the process is running. When the chatbot detects a question about investments, it queries the investment service automatically via HTTP. Investment habits are injected into chat context only after the first investment tool call in a session.

## Configuration

All settings are optional except `OPENAI_API_KEY`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | OpenAI authentication for chat, embeddings, memory extraction, and AI-assisted imports |
| `PORTFOLIO_IMPORT_MODEL` | `gpt-5.6-luna` | Responses API model used for screenshots, PDF, Word, and legacy XLS files |
| `MARKET_DATA_PROVIDER` | `hybrid` | `hybrid` for network sources with demo fallback, or `demo` for deterministic offline data |
| `MARKET_DB_PATH` | `src/data/investment.db` | Custom SQLite database path |
| `MARKET_QUOTE_CACHE_SECONDS` | `30` | Quote cache lifetime for network-backed market data |
| `MARKET_FUND_HISTORY_CACHE_SECONDS` | `30` | OTC-fund NAV-history cache lifetime; kept short so newly published daily NAVs appear promptly |
| `MARKET_REFRESH_SECONDS` | `60` | Background tracker interval; values below 15 seconds are raised to 15 |
| `THUMPER_HOST` | `127.0.0.1` | Chatbot Flask bind address |
| `THUMPER_PORT` | `8080` | Chatbot Flask port |
| `THUMPER_DEBUG` | `1` | Enable Flask debug mode when set to `1` |
| `INVESTMENT_SERVICE_URL` | `http://127.0.0.1:8081` | URL the chatbot uses to reach the investment service |
| `INVESTMENT_HOST` | `127.0.0.1` | Investment service bind address |
| `INVESTMENT_PORT` | `8081` | Investment service port |

For an offline investment demo, set `MARKET_DATA_PROVIDER=demo`. Chat and memory features still require OpenAI access.

## Portfolio Import

The import UI can create either current holdings or watchlist-only entries.

- Maximum file size: 15 MB.
- Maximum normalized rows per import: 500.
- Locally parsed: `.csv`, `.tsv`, `.txt`, `.json`, and `.xlsx`.
- OpenAI-assisted: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.pdf`, `.doc`, `.docx`, and `.xls`.
- A watchlist import needs a symbol or name.
- A holdings import also needs a positive quantity and average cost price.

CSV and spreadsheet columns may use common English or Chinese headers. A minimal holdings CSV looks like this:

```csv
symbol,name,quantity,cost_price,asset_class,subclass,currency,occurred_at
600519,贵州茅台,10,1450,stock,cn,CNY,2026-07-01
AAPL,Apple,5,210,stock,us,USD,2026-07-02
```

Accepted subclass values are `cn`, `hk`, `us`, `exchange_traded`, and `otc`; common labels such as `A股`, `港股`, `美股`, `ETF`, `场内基金`, and `场外基金` are normalized automatically.

A holdings import records one opening `buy` transaction, or one `subscribe` transaction for an OTC fund, using the imported quantity and average cost. It does not reconstruct the account's complete historical trade ledger. Rows are matched against the active market-data provider, and ambiguous or unmatched rows are returned as per-row errors without discarding successful rows.

## How Memory Works

1. **Greeting** — on first use, Thumper introduces itself; on later visits, it can use known core facts for a familiar greeting.
2. **Retrieval** — each user message is embedded and matched against up to five semantically relevant memories.
3. **Prompt augmentation** — retrieved memories are added to the chat system prompt.
4. **Extraction** — after a visible reply, `gpt-4o-mini` extracts useful facts and classifies them as `core` or `episodic`.
5. **Duplicate and conflict handling** — near-identical memories are skipped; sufficiently similar memories are treated as the same topic and the older entry is replaced.
6. **Forgetting** — episodic memory strength follows `importance × e^(−0.1 × days_since_last_access)`. Entries below the pruning threshold are removed on startup.

Investment actions use a separate deterministic memory path. Adding or removing
watchlist items, recording transactions, and importing a portfolio recomputes
evidence-backed habits such as a dominant asset type, repeated theme interest,
or maintaining a broad observation list before holding. These habits are stored
in SQLite, shown as long-term memories, and supplied to chat context. Dismissing
one hides it until the supporting evidence changes. The rules do not infer risk
tolerance, financial capacity, or trading skill from limited activity.
7. **Persistence** — memories are stored in `src/chroma_db/` and survive server restarts until forgotten or manually deleted.

| Category | Typical content | Behaviour |
| --- | --- | --- |
| `core` | Name, goals, preferences, relationships, enduring facts | Does not decay |
| `episodic` | Recent events, temporary plans, passing remarks | Decays over time; half-life is roughly seven days |

## Local Data and Scope

- Chroma memories are stored under `src/chroma_db/`.
- Investment assets, quotes, history, transactions, and predictions are stored in `src/data/investment.db` by default.
- Automatically derived investment habits are stored in the same investment database and remain separate from model-extracted Chroma memories.
- Both locations are ignored by Git.
- The current application is a single-user local prototype with the fixed investment owner `local`; it does not provide authentication or multi-user isolation.
- Memory chat history is process-global and non-persistent, so this version should not be exposed as a multi-user production service.

## Project Structure

```text
├── diary/                         # Contributor work diary
├── tests/
│   ├── test_app.py                # Chat, memory API, and UI route tests
│   ├── test_market.py             # Market database, provider, analytics, and route tests
│   ├── test_memory.py             # Relative-date and episodic-memory tests
│   └── test_portfolio_import.py
└── src/
    ├── investment_habits.py       # Shared: deterministic habit derivation (used by both services)
    ├── main.py                    # Legacy command-line chat client
    ├── extractor.py               # Legacy CLI memory extractor
    ├── requirements.txt
    ├── chroma_db/                 # Auto-created vector memory store (Git-ignored)
    ├── data/                      # Auto-created investment database (Git-ignored)
    ├── chatbot/                   # Chatbot service — run with: python chatbot/app.py
    │   ├── app.py                 # Flask app, chat routes, memory routes
    │   ├── memory.py              # Memory extraction, Chroma storage, retrieval, and decay
    │   ├── investment_tools.py    # HTTP bridge: exposes investment service as LLM tools
    │   ├── static/                # Avatar (thumper.png)
    │   └── templates/             # Chat and memories pages
    └── investment/                # Investment service — run with: python investment/investment_app.py
        ├── investment_app.py      # Flask entry point (port 8081), habits endpoints
        ├── market_routes.py       # Investment pages and JSON/SSE endpoints
        ├── market_service.py      # Portfolio, import, refresh, and analytics orchestration
        ├── market_db.py           # SQLite schema and portfolio calculations
        ├── market_data.py         # Yahoo, Eastmoney, hybrid, and demo providers
        ├── market_tracker.py      # Background refresh worker
        ├── portfolio_import.py    # Local and OpenAI-assisted file parsing
        ├── prediction.py          # Probabilities, risk, backtests, and simulation
        ├── static/                # Market and asset-detail frontend assets
        └── templates/             # Market and asset-detail pages
```

## Tests

From the repository root:

```bash
python -m unittest discover -s tests -v
```

The suite covers chat routes, memory behaviour, portfolio persistence, market providers, analytics, and file imports. Focused provider tests use mocks, and portfolio persistence checks use temporary databases.

## Planned Work

Memory consolidation is planned but not implemented yet. The intended next step is to promote stable, repeatedly accessed `episodic` memories to `core` after threshold, duplicate, conflict, and LLM stability checks.

The longer-term architecture direction is:

```text
Conversation
  → information extraction
  → embeddings and structured parsing
  → vector and relational storage
  → memory scoring and forgetting
  → relevant-memory retrieval
  → prompt augmentation
  → response generation
```

## Diary Setup (Obsidian)

Open `diary/` as an Obsidian vault. Each contributor can keep notes in their own file and use `diary/shared.md` for shared entries.
