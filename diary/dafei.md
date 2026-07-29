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

---

## 2026-07-22
**What I worked on:** 理解了 IMMFlight 新加的投资功能，然后把它重构成一个独立的微服务。

### 背景
IMMFlight 往项目里加了一整套股票追踪功能（portfolio、watchlist、行情数据、预测模型、习惯分析）。原来的代码直接把投资逻辑塞进了 app.py，和 chatbot 主逻辑耦合在一起，难以维护。

### 架构决策

**方案讨论：MCP vs HTTP 工具调用**
- 本来想用 MCP（Anthropic 的 Model Context Protocol，专门为 LLM 做工具服务的协议）
- 但是我朋友在中国大陆，Anthropic API 被限制，项目实际上用的是 OpenAI 兼容接口
- MCP 和 OpenAI function calling 原理一样，协议不同，没必要加额外复杂度
- **决定：用 HTTP + OpenAI function calling，两个独立 Flask 进程通信**

**两服务架构：**
```
用户浏览器
    ↓ HTTP
chatbot (port 8080) — app.py
    ↓ OpenAI API (tool calling)
LLM 决定调用工具
    ↓ HTTP
investment service (port 8081) — investment_app.py
    ↓
market_service → market_data (Eastmoney/Yahoo) + market_db (SQLite)
```

### 改动了哪些文件

**新建 `src/investment_app.py`**
- 独立的 Flask 入口，跑在 port 8081
- 注册 `market_blueprint`（原有的所有投资 API 路由）
- 新增两个接口：`GET /api/habits`、`DELETE /api/habits/<key>`
- 启动 market_tracker 后台线程（每 60s 刷新行情）
- 启动方式：`cd src && python investment_app.py`

**重写 `src/investment_tools.py`**
- 原来直接调用 market_service Python 函数
- 现在改成 HTTP 调用 port 8081
- TOOLS 列表（LLM 看到的工具 schema）不变：get_portfolio、get_asset、search_assets
- `execute()` 通过 requests 转发到投资服务
- `habit_summaries()` 改为 `GET /api/habits`
- 新增 `dismiss_habit()` 调用 `DELETE /api/habits/<key>`
- investment service 没起来时优雅降级：返回 `{"error": "Investment service is not running (port 8081)"}`

**清理 `src/app.py`**
- 删掉所有直接 import 投资模块的代码（market_blueprint、market_service、market_tracker）
- 投资相关功能全部走 investment_tools 的 HTTP 封装
- 主 Flask app 不再 register market_blueprint

### 工具调用流程（LLM 视角）
1. 用户问"我的持仓现在怎么样"
2. app.py 把 TOOLS 列表和对话发给 LLM
3. LLM 返回 `tool_calls: [get_portfolio()]`
4. app.py 调用 `investment_tools.execute("get_portfolio", {})`
5. investment_tools.py 发 HTTP 请求到 port 8081
6. 把结果塞回对话，再次调用 LLM
7. LLM 用工具结果生成最终回复

### 投资习惯注入（被动）
- investment_habits.py 用规则推导用户的投资倾向（不用 LLM）
- 4 条规则：追踪的资产类别、持仓类别、主题偏好、是否先观察再买入
- 习惯存在 SQLite，每次对话开始时被动注入到 system prompt

### 暂缓的事
- `src/` 目录下文件堆在一起很乱，想拆成 `chatbot/` 和 `investment/` 两个子目录
- 需要改 import 路径、Flask 模板路径，工作量不小，先不动

**How to start (两个服务都需要启动):**
1. Terminal 1: `cd src && python investment_app.py` （投资服务，port 8081）
2. Terminal 2: `chatbot`（chatbot 主服务，port 8080）
3. 浏览器打开 http://localhost:8080
