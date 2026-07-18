from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template
from openai import OpenAI
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
    lines = "\n".join(f"{i+1}. {d}" for i, d in enumerate(docs)) if docs else "No memories stored yet."
    return f"<pre style='font-family:monospace;padding:24px'>{lines}</pre>"


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    relevant_memories = memory.retrieve(user_message)
    if relevant_memories:
        memory_block = "Relevant memories about the user:\n" + "\n".join(f"- {m}" for m in relevant_memories)
        system_prompt = f"{_BASE_SYSTEM_PROMPT}\n\n{memory_block}"
    else:
        system_prompt = _BASE_SYSTEM_PROMPT

    conversation_history.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}] + conversation_history,
    )

    assistant_message = response.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": assistant_message})

    memories_saved = memory.extract_and_store(user_message, assistant_message)

    return jsonify({"response": assistant_message, "memories_saved": memories_saved})


if __name__ == "__main__":
    app.run(debug=True, port=8080)
