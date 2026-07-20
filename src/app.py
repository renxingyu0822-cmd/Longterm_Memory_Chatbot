from flask import Flask, request, jsonify, render_template
from markupsafe import escape
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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/memories")
def memories():
    results = memory.collection.get(include=["documents", "metadatas"])
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])
    if not docs:
        return "<pre style='font-family:monospace;padding:24px'>No memories stored yet.</pre>"

    core = [(d, m) for d, m in zip(docs, metas) if m and m.get("category") == "core"]
    episodic = [(d, m) for d, m in zip(docs, metas) if not m or m.get("category") != "core"]

    def fmt(entries):
        return "\n".join(
            f"  {i+1}. [{(m or {}).get('importance', 0):.2f}] {escape(str(d))}"
            for i, (d, m) in enumerate(entries)
        ) or "  (none)"

    body = f"CORE (permanent)\n{fmt(core)}\n\nEPISODIC (may be forgotten)\n{fmt(episodic)}"
    return f"<pre style='font-family:monospace;padding:24px'>{body}</pre>"


@app.route("/greet")
def greet():
    is_first_meeting = memory.collection.count() == 0
    if is_first_meeting:
        prompt = "This is your first time meeting this user. Greet them warmly, introduce yourself as Thumper, and ask for their name. One or two sentences max."
    else:
        known = memory.collection.get(include=["documents", "metadatas"])
        core_facts = [
            d for d, m in zip(known["documents"], known["metadatas"])
            if m and m.get("category") == "core"
        ]
        facts_block = "\n".join(f"- {f}" for f in core_facts[:5]) if core_facts else ""
        prompt = f"Welcome back the user like a friend you already know. Keep it short and casual — one or two sentences. Don't list what you know; just greet them naturally.{chr(10) + 'What you know: ' + chr(10) + facts_block if facts_block else ''}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _BASE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    message = response.choices[0].message.content or "Hey! What's up?"
    conversation_history.append({"role": "assistant", "content": message})
    return jsonify({"response": message})


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

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
        )
    except Exception:
        app.logger.exception("Failed to generate a chat response")
        return jsonify({"error": "The chat service is temporarily unavailable"}), 502

    assistant_message = response.choices[0].message.content
    if not assistant_message:
        app.logger.error("The chat model returned an empty response")
        return jsonify({"error": "The chat service returned an empty response"}), 502

    conversation_history.append(user_turn)
    conversation_history.append({"role": "assistant", "content": assistant_message})

    try:
        memories_saved = memory.extract_and_store(user_message, assistant_message)
    except Exception:
        app.logger.exception("Failed to extract or store memories")
        memories_saved = []

    return jsonify({"response": assistant_message, "memories_saved": memories_saved})


if __name__ == "__main__":
    app.run(debug=True, port=8080)
