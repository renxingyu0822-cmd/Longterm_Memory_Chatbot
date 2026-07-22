import re
import json
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv

_LANG_NAMES = {
    "en": "English",
    "zh": "Chinese (Mandarin)",
    "de": "German",
}

_LANG_INSTRUCTION = {
    "en": "IMPORTANT: You MUST respond in English only. Do not use any other language, even if the conversation history contains messages in another language.",
    "zh": "重要：你必须只用中文回复。无论对话历史中有任何其他语言的内容，都不得使用其他语言。",
    "de": "WICHTIG: Du MUSST ausschließlich auf Deutsch antworten. Verwende keine andere Sprache, auch wenn der Gesprächsverlauf Nachrichten in einer anderen Sprache enthält.",
}

_MEMORY_UI = {
    "en": {
        "title": "Memory Bank",
        "back": "← Back to chat",
        "eyebrow": "Memory archive",
        "heading": "Memory Bank",
        "subtitle": "Long-term memories build a lasting understanding of you. Short-term memories capture recent events. Together they help Thumper pick up every conversation naturally.",
        "memories_count": "memories",
        "demo_note": "This is sample data — nothing here has been written to your real memory bank.",
        "demo_link": "View real memories",
        "core_title": "Long-term Memory",
        "core_copy": "Core facts · Kept forever",
        "core_empty_title": "No long-term memories yet",
        "core_empty_body": "Tell Thumper your name, preferences, or long-term goals.",
        "episodic_title": "Short-term Memory",
        "episodic_copy": "Recent events · Fades over time",
        "episodic_empty_title": "No short-term memories yet",
        "episodic_empty_body": "Temporary plans and recent events will appear here.",
        "importance": "Importance",
        "never_forgotten": "Never forgotten",
        "will_fade": "Will fade",
        "view_demo": "View a demo",
    },
    "zh": {
        "title": "记忆库",
        "back": "← 返回聊天",
        "eyebrow": "记忆存档",
        "heading": "记忆库",
        "subtitle": "长期记忆塑造持续的了解，短期记忆保留眼前的事件。两类记忆共同帮助 Thumper 更自然地延续每一次对话。",
        "memories_count": "条记忆",
        "demo_note": "当前展示的是示例数据，不会写入你的真实记忆库。",
        "demo_link": "查看真实记忆",
        "core_title": "长期记忆",
        "core_copy": "核心信息 · 永久保留",
        "core_empty_title": "还没有长期记忆",
        "core_empty_body": "告诉 Thumper 你的名字、喜好或长期目标。",
        "episodic_title": "短期记忆",
        "episodic_copy": "近期事件 · 随时间衰减",
        "episodic_empty_title": "还没有短期记忆",
        "episodic_empty_body": "临时计划和近期事件会出现在这里。",
        "importance": "重要度",
        "never_forgotten": "不会遗忘",
        "will_fade": "会衰减",
        "view_demo": "查看完整示例",
    },
    "de": {
        "title": "Gedächtnisbank",
        "back": "← Zurück zum Chat",
        "eyebrow": "Gedächtnisarchiv",
        "heading": "Gedächtnisbank",
        "subtitle": "Langzeitgedächtnisse bauen ein dauerhaftes Verständnis von dir auf. Kurzzeitgedächtnisse erfassen aktuelle Ereignisse. Gemeinsam helfen sie Thumper, jedes Gespräch natürlich fortzusetzen.",
        "memories_count": "Erinnerungen",
        "demo_note": "Dies sind Beispieldaten — nichts davon wurde in deine echte Gedächtnisbank geschrieben.",
        "demo_link": "Echte Erinnerungen anzeigen",
        "core_title": "Langzeitgedächtnis",
        "core_copy": "Kernfakten · Für immer gespeichert",
        "core_empty_title": "Noch keine Langzeitgedächtnisse",
        "core_empty_body": "Erzähl Thumper deinen Namen, deine Vorlieben oder langfristige Ziele.",
        "episodic_title": "Kurzzeitgedächtnis",
        "episodic_copy": "Aktuelle Ereignisse · Verblasst mit der Zeit",
        "episodic_empty_title": "Noch keine Kurzzeitgedächtnisse",
        "episodic_empty_body": "Vorübergehende Pläne und aktuelle Ereignisse erscheinen hier.",
        "importance": "Wichtigkeit",
        "never_forgotten": "Nie vergessen",
        "will_fade": "Wird verblassen",
        "view_demo": "Demo ansehen",
    },
}

load_dotenv()

import memory

app = Flask(__name__)
client = OpenAI()
conversation_history = []

pruned = memory.forget()
if pruned:
    app.logger.info("Pruned %d stale episodic memories on startup", pruned)

_BASE_SYSTEM_PROMPT = """Your name is Thumper. You are a witty, relaxed companion who genuinely knows the user. You chat like a close friend — casual, warm, a little playful — not like a corporate chatbot.

Guidelines:
- Keep it conversational. Short sentences are fine. You don't need to answer every question with a list.
- Use the user's memories naturally — weave them in without making it feel like you're reading from a file. Don't announce "I remember that..."; just use what you know.
- Match the user's energy. If they're being silly, roll with it. If they're venting, dial back the jokes.
- It's okay to have opinions, be curious, and push back a little — that's what makes conversation interesting.
- Never be stiff, overly formal, or start responses with "Certainly!" or "Of course!".

Getting to know the user:
- If you don't know the user's name, find a natural moment early in the conversation to ask.
- If you don't know their gender or preferred pronouns, pick it up from context or ask casually when it feels right.
- Other useful things to learn over time: what they do, where they're from, their interests, age group.
- Never ask multiple questions at once — one thing at a time, woven naturally into the conversation. Don't make it feel like a form.
- IMPORTANT: Do NOT end your reply with a question every time. Most replies should end with a statement, reaction, or opinion — not a question. Only ask something when you are genuinely curious and it feels completely natural. Ending every message with a question feels robotic and annoying."""

_MEMORY_PAGE_COPY = {
    "en": {
        "html_lang": "en",
        "page_title": "Thumper · Memories",
        "nav_label": "Page navigation",
        "back": "← Back to chat",
        "eyebrow": "Memory archive",
        "heading": "Memories",
        "subtitle": "Long-term memories build lasting understanding, while short-term memories preserve recent events. Together they help Thumper continue every conversation naturally.",
        "total_unit": "memories",
        "demo_notice": "You are viewing sample data. It will not be added to your real memories.",
        "view_real": "View real memories",
        "core_heading": "Long-term memory",
        "core_copy": "Core facts · Kept permanently",
        "importance": "Importance",
        "permanent": "Never forgotten",
        "core_empty_heading": "No long-term memories yet",
        "core_empty_copy": "Tell Thumper your name, preferences, or long-term goals.",
        "episodic_heading": "Short-term memory",
        "episodic_copy": "Recent events · Fades over time",
        "decays": "Fades over time",
        "episodic_empty_heading": "No short-term memories yet",
        "episodic_empty_copy": "Temporary plans and recent events will appear here.",
        "view_demo": "View full example",
    },
    "zh": {
        "html_lang": "zh-CN",
        "page_title": "Thumper · 记忆库",
        "nav_label": "页面导航",
        "back": "← 返回聊天",
        "eyebrow": "记忆档案",
        "heading": "记忆库",
        "subtitle": "长期记忆塑造持续的了解，短期记忆保留眼前的事件。两类记忆共同帮助 Thumper 更自然地延续每一次对话。",
        "total_unit": "条记忆",
        "demo_notice": "当前展示的是示例数据，不会写入你的真实记忆库。",
        "view_real": "查看真实记忆",
        "core_heading": "长期记忆",
        "core_copy": "核心信息 · 永久保留",
        "importance": "重要度",
        "permanent": "不会遗忘",
        "core_empty_heading": "还没有长期记忆",
        "core_empty_copy": "告诉 Thumper 你的名字、喜好或长期目标。",
        "episodic_heading": "短期记忆",
        "episodic_copy": "近期事件 · 随时间衰减",
        "decays": "会衰减",
        "episodic_empty_heading": "还没有短期记忆",
        "episodic_empty_copy": "临时计划和近期事件会出现在这里。",
        "view_demo": "查看完整示例",
    },
    "de": {
        "html_lang": "de",
        "page_title": "Thumper · Erinnerungen",
        "nav_label": "Seitennavigation",
        "back": "← Zurück zum Chat",
        "eyebrow": "Erinnerungsarchiv",
        "heading": "Erinnerungen",
        "subtitle": "Langzeiterinnerungen schaffen dauerhaftes Verständnis, während Kurzzeiterinnerungen aktuelle Ereignisse bewahren. Gemeinsam helfen sie Thumper, jedes Gespräch natürlich fortzusetzen.",
        "total_unit": "Erinnerungen",
        "demo_notice": "Du siehst Beispieldaten. Sie werden nicht in deinen echten Erinnerungen gespeichert.",
        "view_real": "Echte Erinnerungen ansehen",
        "core_heading": "Langzeitgedächtnis",
        "core_copy": "Kerninformationen · Dauerhaft gespeichert",
        "importance": "Wichtigkeit",
        "permanent": "Bleibt erhalten",
        "core_empty_heading": "Noch keine Langzeiterinnerungen",
        "core_empty_copy": "Erzähle Thumper deinen Namen, deine Vorlieben oder langfristigen Ziele.",
        "episodic_heading": "Kurzzeitgedächtnis",
        "episodic_copy": "Aktuelle Ereignisse · Verblasst mit der Zeit",
        "decays": "Verblasst",
        "episodic_empty_heading": "Noch keine Kurzzeiterinnerungen",
        "episodic_empty_copy": "Vorübergehende Pläne und aktuelle Ereignisse erscheinen hier.",
        "view_demo": "Vollständiges Beispiel ansehen",
    },
}


def _chat_language(value):
    return value if value in _LANG_INSTRUCTION else "en"


_MULTI_MSG_INSTRUCTION = """
MULTI-MESSAGE HANDLING:
Users sometimes send thoughts as quick bursts. Judge whether the user is mid-thought or has said enough to respond.

Begin your response with exactly one of:
  ACTION: WAIT    — ONLY when the message is a bare lead-in with clearly more coming. These are rhetorical openers, not real questions — the user is dangling a hook.
  ACTION: REPLY   — whenever the user has said something with actual content. Default to this. When in doubt, reply.

CRITICAL: The ACTION prefix must ALWAYS be written in English — "ACTION: WAIT" or "ACTION: REPLY" — regardless of what language you are replying in. Never translate it.

WAIT triggers (bare hooks with no real content):
  English: "hi", "hey", "you know what?", "guess what", "omg", "so,", a lone emoji
  Chinese: "你知道吗", "猜猜怎么了", "你猜怎么着", "哎", "诶", "哦对了", lone "哈哈"
  German: "weißt du was", "rate mal", lone "ey"

KEY RULE — always use ACTION: REPLY for:
  • Any greeting with a time-of-day word ("good morning", "晚上好", "guten morgen")
  • Any message that addresses you by name ("hi thumper", "嗨 thumper")
  • Any statement of feeling, fact, or event ("i'm tired", "刚到家", "ich bin müde")
  • Any question with actual content ("what do you think about X?", "你觉得X怎么样?")
  • Multiple buffered messages where the latest adds real content beyond the opener

When a message contains multiple lines, treat each line as a separate text — judge them together.
Write your reply as natural prose. Do not use any separators — the splitting is handled automatically.

Examples:
  "hi" → ACTION: WAIT
  "you know what?" → ACTION: WAIT
  "你知道吗" → ACTION: WAIT
  "猜猜怎么了" → ACTION: WAIT
  "good morning!" → ACTION: REPLY\\nMorning! How's it going?
  "i'm tired" → ACTION: REPLY\\nAw, rough day?
  "你好呀" → ACTION: REPLY\\n嗨！怎么了？
  "hi\\nyou know what?\\ni ran into my high school teacher" → ACTION: REPLY\\nNo way! Did you two actually talk?
  "你知道吗\\n我今天遇见了我的高中老师" → ACTION: REPLY\\n真的假的！你们说话了吗？
"""


# Splits on English sentence ends (punct + space) OR CJK sentence ends (no space needed)
_SENT_RE = re.compile(r'(?<=[.!?])\s+|(?<=[。！？])')


def split_into_blocks(text: str) -> list[str]:
    """Split a reply into 1–3 natural chat message blocks (English + CJK aware)."""
    sentences = [s.strip() for s in _SENT_RE.split(text.strip()) if s.strip()]

    if len(sentences) <= 1:
        return [text.strip()]

    # CJK text has no spaces between sentences; English needs a space when re-joining
    is_cjk = any('一' <= c <= '鿿' for c in text)
    join = (lambda parts: ''.join(parts)) if is_cjk else (lambda parts: ' '.join(parts))

    def is_q(s: str) -> bool:
        return s.endswith(('?', '？'))

    def is_short_exclaim(s: str) -> bool:
        # ≤5 space-separated tokens (English) OR ≤10 chars total (CJK)
        return s.endswith(('!', '！')) and (len(s.split()) <= 5 or len(s) <= 10)

    # Rule 1: short exclamatory opener → its own first block
    if is_short_exclaim(sentences[0]):
        opener, rest = sentences[0], sentences[1:]
        if not rest:
            return [opener]
        # Split a trailing question off into a third block if there's content before it
        if len(rest) >= 2 and is_q(rest[-1]):
            return [opener, join(rest[:-1]), rest[-1]]
        return [opener, join(rest)]

    # Rule 2: split before the FIRST question that has statement content before it
    for i, s in enumerate(sentences):
        if is_q(s) and i > 0:
            return [join(sentences[:i]), join(sentences[i:])]

    # Rule 3: 3+ non-question sentences → split at midpoint
    if len(sentences) >= 3:
        mid = len(sentences) // 2
        return [join(sentences[:mid]), join(sentences[mid:])]

    # Rule 4: exactly 2 sentences → two blocks
    return [sentences[0], sentences[1]]


def drop_trailing_question(blocks: list[str]) -> list[str]:
    """Remove the last block if it is purely a question, keeping at least one block."""
    if len(blocks) <= 1:
        return blocks
    last = blocks[-1].strip()
    if last.endswith(('?', '？')):
        return blocks[:-1]
    return blocks


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/memories")
def memories():
    is_demo = request.args.get("demo") == "1"
    lang = request.args.get("lang", "zh")
    if lang not in _MEMORY_PAGE_COPY:
        lang = "zh"

    if is_demo:
        now = datetime.now().astimezone()
        tomorrow = (now + timedelta(days=1)).date().isoformat()
        today = now.date().isoformat()
        demo_text = {
            "en": [
                "The user's name is Alex",
                "The user is a software engineer living in Shanghai",
                "The user likes pour-over coffee and weekend hikes",
                f"The user has a project meeting tomorrow ({tomorrow}) at 3 PM",
                f"The user felt tired from work today ({today})",
            ],
            "zh": [
                "用户的名字是小明",
                "用户是一名软件工程师，目前居住在上海",
                "用户喜欢手冲咖啡和周末徒步",
                f"用户明天（{tomorrow}）下午 3 点参加项目会议",
                f"用户今天（{today}）工作有些疲惫",
            ],
            "de": [
                "Der Benutzer heißt Alex",
                "Der Benutzer ist Softwareentwickler und lebt in Shanghai",
                "Der Benutzer mag Filterkaffee und Wochenendwanderungen",
                f"Der Benutzer hat morgen ({tomorrow}) um 15 Uhr eine Projektbesprechung",
                f"Der Benutzer war heute ({today}) von der Arbeit müde",
            ],
        }[lang]
        raw_entries = [
            (demo_text[0], {"category": "core", "importance": 0.98}),
            (demo_text[1], {"category": "core", "importance": 0.90}),
            (demo_text[2], {"category": "core", "importance": 0.82}),
            (demo_text[3], {"category": "episodic", "importance": 0.76, "event_date": tomorrow}),
            (demo_text[4], {"category": "episodic", "importance": 0.48, "event_date": today}),
        ]
    else:
        results = memory.collection.get(include=["documents", "metadatas"])
        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        if len(metas) < len(docs):
            metas = [*metas, *([None] * (len(docs) - len(metas)))]
        raw_entries = list(zip(docs, metas))

    def view_model(document, metadata):
        meta = metadata or {}
        importance = max(0.0, min(1.0, float(meta.get("importance", 0))))
        return {
            "text": str(document),
            "importance": importance,
            "importance_percent": round(importance * 100),
            "event_date": meta.get("event_date"),
            "category": meta.get("category", "episodic"),
        }

    entries = [view_model(document, metadata) for document, metadata in raw_entries]
    core = [entry for entry in entries if entry["category"] == "core"]
    episodic = [entry for entry in entries if entry["category"] != "core"]

    lang = request.args.get("lang", "en")
    if lang not in _MEMORY_UI:
        lang = "en"

    return render_template(
        "memories.html",
        core_memories=core,
        episodic_memories=episodic,
        is_demo=is_demo,
        total=len(entries),
        lang=lang,
        copy=_MEMORY_PAGE_COPY[lang],
    )


@app.route("/reset", methods=["POST"])
def reset():
    conversation_history.clear()
    return jsonify({"ok": True})


@app.route("/greet")
def greet():
    lang = _chat_language(request.args.get("lang"))
    lang_note = _LANG_INSTRUCTION[lang]

    is_first_meeting = memory.collection.count() == 0
    if is_first_meeting:
        prompt = "This is your first time meeting this user. Greet them warmly, introduce yourself as Thumper, and ask for their name. One or two sentences max."
    else:
        known = memory.collection.get(include=["documents", "metadatas"])
        known_docs = known.get("documents") or []
        known_metas = known.get("metadatas") or []
        core_facts = [
            d for d, m in zip(known_docs, known_metas)
            if m and m.get("category") == "core"
        ]
        facts_block = "\n".join(f"- {f}" for f in core_facts[:5]) if core_facts else ""
        prompt = f"Welcome back the user like a friend you already know. Keep it short and casual — one or two sentences. Don't list what you know; just greet them naturally.{chr(10) + 'What you know: ' + chr(10) + facts_block if facts_block else ''}"

    system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\nLANGUAGE: {lang_note}"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    fallback = {
        "en": "Hey! What's up?",
        "zh": "嗨！最近怎么样？",
        "de": "Hey! Wie geht's?",
    }[lang]
    message = response.choices[0].message.content or fallback
    conversation_history.append({"role": "assistant", "content": message})
    return jsonify({"response": message})


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    raw_messages = payload.get("messages")
    if raw_messages is None:
        raw_msg = payload.get("message")
        raw_messages = [raw_msg] if isinstance(raw_msg, str) else None
    if not isinstance(raw_messages, list) or not raw_messages:
        return jsonify({"error": "Provide a non-empty 'messages' list"}), 400

    messages = [m.strip() for m in raw_messages if isinstance(m, str) and m.strip()]
    if not messages:
        return jsonify({"error": "Empty messages"}), 400

    user_input = "\n".join(messages)

    lang = _chat_language(payload.get("lang"))
    lang_note = _LANG_INSTRUCTION[lang]

    try:
        relevant_memories = memory.retrieve(user_input)
    except Exception:
        app.logger.exception("Failed to retrieve memories")
        return jsonify({"error": "The chat service is temporarily unavailable"}), 502

    is_first_meeting = memory.collection.count() == 0

    if is_first_meeting:
        system_prompt = (
            _BASE_SYSTEM_PROMPT + _MULTI_MSG_INSTRUCTION
            + f"\n\nLANGUAGE: {lang_note}\n\nThis is your first time meeting this user. "
            "You know nothing about them yet. Your priority is to learn their name and get to know them — "
            "ask warmly and naturally, like meeting someone new for the first time. "
            "Say 'nice to meet you' once you know their name."
        )
    elif relevant_memories:
        memory_block = "What you know about the user:\n" + "\n".join(f"- {m}" for m in relevant_memories)
        system_prompt = f"{_BASE_SYSTEM_PROMPT}{_MULTI_MSG_INSTRUCTION}\n\nLANGUAGE: {lang_note}\n\n{memory_block}"
    else:
        system_prompt = f"{_BASE_SYSTEM_PROMPT}{_MULTI_MSG_INSTRUCTION}\n\nLANGUAGE: {lang_note}"

    try:
        from typing import cast
        from openai.types.chat import ChatCompletionMessageParam
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=cast(
                list[ChatCompletionMessageParam],
                [{"role": "system", "content": system_prompt}]
                + conversation_history
                + [{"role": "user", "content": user_input}]
            ),
        )
    except Exception:
        app.logger.exception("Failed to generate a chat response")
        return jsonify({"error": "The chat service is temporarily unavailable"}), 502

    raw_response = response.choices[0].message.content
    if not raw_response:
        app.logger.error("The chat model returned an empty response")
        return jsonify({"error": "The chat service returned an empty response"}), 502

    # Parse ACTION: WAIT / ACTION: REPLY — also catches Chinese translations as fallback
    match = re.match(
        r'^(?:ACTION|行动)[：:]\s*(WAIT|等待|REPLY|回复)\s*\n?(.*)',
        raw_response.strip(), re.DOTALL | re.IGNORECASE
    )
    if match:
        keyword = match.group(1).upper()
        action = "WAIT" if keyword in ("WAIT", "等待") else "REPLY"
        reply_text = match.group(2).strip()
    else:
        action = "REPLY"
        reply_text = raw_response.strip()

    if action == "WAIT":
        return jsonify({"action": "wait"})

    blocks = drop_trailing_question(split_into_blocks(reply_text))
    assistant_message = "\n".join(blocks)
    for msg in messages:
        conversation_history.append({"role": "user", "content": msg})
    conversation_history.append({"role": "assistant", "content": assistant_message})

    try:
        memories_saved = memory.extract_and_store(user_input, assistant_message)
    except Exception:
        app.logger.exception("Failed to extract or store memories")
        memories_saved = []

    return jsonify({"action": "reply", "blocks": blocks, "memories_saved": memories_saved})


@app.route("/remember", methods=["POST"])
def remember():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    user_message = payload.get("user_message")
    assistant_message = payload.get("assistant_message")
    if not isinstance(user_message, str) or not user_message.strip():
        return jsonify({"error": "User message must be a non-empty string"}), 400
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        return jsonify({"error": "Assistant message must be a non-empty string"}), 400

    try:
        memories_saved = memory.extract_and_store(
            user_message.strip(), assistant_message.strip()
        )
    except Exception:
        app.logger.exception("Failed to extract or store memories")
        return jsonify({"error": "Memory storage is temporarily unavailable"}), 502

    return jsonify({"memories_saved": memories_saved})


@app.route("/nudge", methods=["POST"])
def nudge():
    payload = request.get_json(silent=True) or {}

    raw_messages = payload.get("messages", [])
    messages = [m.strip() for m in raw_messages if isinstance(m, str) and m.strip()]

    lang = payload.get("lang", "en")
    if lang not in _LANG_INSTRUCTION:
        lang = "en"
    lang_note = _LANG_INSTRUCTION[lang]

    if messages:
        msgs_text = "\n".join(f'- "{m}"' for m in messages)
        nudge_prompt = (
            f"The user sent these messages but then went quiet for 20 seconds:\n{msgs_text}\n\n"
            "They seemed to be building up to something. Give them a very light, curious nudge — "
            "like a friend who's just quietly waiting, not demanding. "
            "Keep it short and low-pressure: a simple question or a soft '...?' style prompt. "
            "Do NOT use phrases like 'don't leave me hanging' or anything that sounds impatient or pushy. "
            "No ACTION: prefix."
        )
    else:
        nudge_prompt = (
            "The user went quiet. Give them a soft, low-pressure check-in — one casual question or short prompt. "
            "Not pushy. No ACTION: prefix."
        )

    system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\nLANGUAGE: {lang_note}"

    try:
        from typing import cast
        from openai.types.chat import ChatCompletionMessageParam
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=cast(
                list[ChatCompletionMessageParam],
                [{"role": "system", "content": system_prompt}]
                + conversation_history
                + [{"role": "user", "content": nudge_prompt}]
            ),
        )
    except Exception:
        app.logger.exception("Failed to generate nudge")
        return jsonify({"error": "The chat service is temporarily unavailable"}), 502

    nudge_message = (response.choices[0].message.content or "so... what's up?").strip()

    for msg in messages:
        conversation_history.append({"role": "user", "content": msg})
    conversation_history.append({"role": "assistant", "content": nudge_message})

    blocks = [b.strip() for b in nudge_message.split("|||") if b.strip()]
    if not blocks:
        blocks = [nudge_message]

    return jsonify({"blocks": blocks})


if __name__ == "__main__":
    app.run(debug=True, port=8080)
