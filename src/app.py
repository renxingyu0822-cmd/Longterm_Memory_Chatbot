import json
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from dotenv import load_dotenv

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
- Never ask multiple questions at once — one thing at a time, woven naturally into the conversation. Don't make it feel like a form."""

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

_LANGUAGE_INSTRUCTIONS = {
    "en": "Reply in English unless the user explicitly asks for another language.",
    "zh": "Use natural Simplified Chinese for every reply unless the user explicitly asks for another language.",
    "de": "Reply in natural German unless the user explicitly asks for another language.",
}

_REPLY_BUBBLES_INSTRUCTION = """Choose how many chat bubbles the reply needs.
- Usually return one concise bubble.
- When the buffered user messages contain distinct questions or topics that are clearer answered separately, return a separate bubble for each, in the same order.
- Keep closely related follow-up fragments together instead of mechanically creating one bubble per user message.
- Return at most ten bubbles and do not repeat information across them."""

_REPLY_BUBBLES_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "chat_bubbles",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "replies": {
                    "type": "array",
                    "description": "One to ten natural chat bubbles, in display order.",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 10,
                }
            },
            "required": ["replies"],
            "additionalProperties": False,
        },
    },
}


def _chat_language(value):
    return value if value in _LANGUAGE_INSTRUCTIONS else "en"


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

    return render_template(
        "memories.html",
        core_memories=core,
        episodic_memories=episodic,
        is_demo=is_demo,
        total=len(entries),
        lang=lang,
        copy=_MEMORY_PAGE_COPY[lang],
    )


@app.route("/greet")
def greet():
    lang = _chat_language(request.args.get("lang"))
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

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"{_BASE_SYSTEM_PROMPT}\n\n{_LANGUAGE_INSTRUCTIONS[lang]}",
            },
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

    lang = _chat_language(payload.get("lang"))

    raw_messages = payload.get("messages")
    if raw_messages is not None:
        if not isinstance(raw_messages, list) or not raw_messages:
            return jsonify({"error": "Messages must be a non-empty list"}), 400
        if len(raw_messages) > 10:
            return jsonify({"error": "A message batch can contain at most 10 messages"}), 400
        if not all(isinstance(message, str) for message in raw_messages):
            return jsonify({"error": "Every message must be a string"}), 400
        messages = [message.strip() for message in raw_messages]
        if any(not message for message in messages):
            return jsonify({"error": "Messages cannot be empty"}), 400
        user_message = "\n".join(messages)
    else:
        raw_message = payload.get("message")
        if not isinstance(raw_message, str):
            return jsonify({"error": "Message must be a string"}), 400

        user_message = raw_message.strip()
        if not user_message:
            return jsonify({"error": "Empty message"}), 400

    try:
        relevant_memories = memory.retrieve(user_message)
    except Exception:
        app.logger.exception("Failed to retrieve memories")
        return jsonify({"error": "The chat service is temporarily unavailable"}), 502

    is_first_meeting = memory.collection.count() == 0

    if is_first_meeting:
        system_prompt = _BASE_SYSTEM_PROMPT + "\n\nThis is your first time meeting this user. You know nothing about them yet. Your priority is to learn their name and get to know them — ask warmly and naturally, like meeting someone new for the first time. Say 'nice to meet you' once you know their name."
    elif relevant_memories:
        memory_block = "What you know about the user:\n" + "\n".join(f"- {m}" for m in relevant_memories)
        system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{memory_block}"
    else:
        system_prompt = _BASE_SYSTEM_PROMPT

    system_prompt = (
        f"{system_prompt}\n\n{_LANGUAGE_INSTRUCTIONS[lang]}"
        f"\n\n{_REPLY_BUBBLES_INSTRUCTION}"
    )

    user_turn = {"role": "user", "content": user_message}
    try:
        from typing import cast
        from openai.types.chat import ChatCompletionMessageParam
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=cast(
                list[ChatCompletionMessageParam],
                [{"role": "system", "content": system_prompt}]
                + conversation_history
                + [user_turn]
            ),
            response_format=_REPLY_BUBBLES_FORMAT,
        )
    except Exception:
        app.logger.exception("Failed to generate a chat response")
        return jsonify({"error": "The chat service is temporarily unavailable"}), 502

    raw_response = response.choices[0].message.content
    if not raw_response:
        app.logger.error("The chat model returned an empty response")
        return jsonify({"error": "The chat service returned an empty response"}), 502

    try:
        structured_response = json.loads(raw_response)
        replies = [
            reply.strip()
            for reply in structured_response["replies"]
            if isinstance(reply, str) and reply.strip()
        ]
    except (json.JSONDecodeError, KeyError, TypeError):
        app.logger.error("The chat model returned an invalid structured response")
        return jsonify({"error": "The chat service returned an invalid response"}), 502

    if not 1 <= len(replies) <= 10:
        app.logger.error("The chat model returned an invalid number of reply bubbles")
        return jsonify({"error": "The chat service returned an invalid response"}), 502

    assistant_message = "\n".join(replies)

    conversation_history.append(user_turn)
    conversation_history.append({"role": "assistant", "content": assistant_message})

    return jsonify({"response": assistant_message, "responses": replies})


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


if __name__ == "__main__":
    app.run(debug=True, port=8080)
