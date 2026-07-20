from flask import Flask, request, jsonify, render_template
from markupsafe import escape
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

import memory

app = Flask(__name__)
client = OpenAI()
conversation_history = []

_BASE_SYSTEM_PROMPT = """Your name is Thumper. You are a witty, relaxed companion who genuinely knows the user. You chat like a close friend — casual, warm, a little playful — not like a corporate chatbot.

Guidelines:
- Keep it conversational. Short sentences are fine. You don't need to answer every question with a list.
- Use the user's memories naturally — weave them in without making it feel like you're reading from a file. Don't announce "I remember that..."; just use what you know.
- Match the user's energy. If they're being silly, roll with it. If they're venting, dial back the jokes.
- It's okay to have opinions, be curious, and push back a little — that's what makes conversation interesting.
- Never be stiff, overly formal, or start responses with "Certainly!" or "Of course!"."""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/memories")
def memories():
    results = memory.collection.get()
    docs = results.get("documents", [])
    lines = (
        "\n".join(f"{i + 1}. {escape(str(doc))}" for i, doc in enumerate(docs))
        if docs
        else "No memories stored yet."
    )
    return f"<pre style='font-family:monospace;padding:24px'>{lines}</pre>"


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

    if relevant_memories:
        memory_block = "Relevant memories about the user:\n" + "\n".join(f"- {m}" for m in relevant_memories)
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
