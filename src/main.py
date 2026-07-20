import uuid
from dotenv import load_dotenv
from openai import OpenAI
from typing import cast, Any
import memory
import extractor

load_dotenv()

client = OpenAI()
conversation_history: list = []


def build_system_prompt(memories: list[str]) -> str:
    base = "You are a helpful assistant with long-term memory."
    if not memories:
        return base
    memory_block = "\n".join(f"- {m}" for m in memories)
    return f"{base}\n\nWhat you remember about the user:\n{memory_block}"


def chat(user_message: str) -> str:
    relevant_memories = memory.retrieve(user_message)
    system_prompt = build_system_prompt(relevant_memories)

    conversation_history.append({"role": "user", "content": user_message})

    # The OpenAI client typings expect specific message param types; cast to Any to satisfy the type checker
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=cast(Any, [{"role": "system", "content": system_prompt}] + conversation_history),
    )

    assistant_message = response.choices[0].message.content
    if not assistant_message:
        raise RuntimeError("The chat model returned an empty response")

    conversation_history.append({"role": "assistant", "content": assistant_message})

    new_memories = extractor.extract(user_message, assistant_message)
    for mem in new_memories:
        memory.store(mem, memory_id=str(uuid.uuid4()))

    return assistant_message


def main():
    print("Long-Term Memory Chatbot (type 'quit' to exit)\n")
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        response = chat(user_input)
        print(f"Bot: {response}\n")


if __name__ == "__main__":
    main()
