from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

SYSTEM_PROMPT = """Extract memorable facts from this conversation turn.
Return one fact per line. Focus on: user preferences, personal details, goals, habits, or important events.
If nothing is worth remembering, return an empty response.
Be concise — each fact should be one sentence."""


def extract(user_message: str, assistant_response: str) -> list[str]:
    conversation = f"User: {user_message}\nAssistant: {assistant_response}"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": conversation},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content
    if not content:
        return []

    raw = content.strip()
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]
