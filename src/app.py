import uuid
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import memory
import extractor

load_dotenv()

app = Flask(__name__)
client = OpenAI()
conversation_history = []


def build_system_prompt(memories: list[str]) -> str:
    base = "You are a helpful assistant with long-term memory."
    if not memories:
        return base
    memory_block = "\n".join(f"- {m}" for m in memories)
    return f"{base}\n\nWhat you remember about the user:\n{memory_block}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    relevant_memories = memory.retrieve(user_message)
    system_prompt = build_system_prompt(relevant_memories)

    conversation_history.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}] + conversation_history,
    )

    assistant_message = response.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": assistant_message})

    new_memories = extractor.extract(user_message, assistant_message)
    for mem in new_memories:
        memory.store(mem, memory_id=str(uuid.uuid4()))

    return jsonify({"response": assistant_message, "memories_saved": new_memories})


if __name__ == "__main__":
    app.run(debug=True, port=8080)
