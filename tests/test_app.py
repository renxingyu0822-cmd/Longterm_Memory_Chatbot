import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import app  # noqa: E402


class ChatRouteTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        app.conversation_history.clear()
        self.client = app.app.test_client()

    def test_rejects_non_object_json(self):
        response = self.client.post("/chat", json=[])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Request body must be a JSON object"},
        )

    def test_rejects_non_string_message(self):
        response = self.client.post("/chat", json={"message": 42})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Message must be a string"})

    @patch("app.memory.extract_and_store", return_value=["User likes tea"])
    @patch("app.memory.retrieve", return_value=[])
    @patch("app.client.chat.completions.create")
    def test_successful_chat(self, create_completion, _retrieve, _extract):
        create_completion.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="Tea sounds good."))
            ]
        )

        response = self.client.post("/chat", json={"message": " I like tea "})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "response": "Tea sounds good.",
                "memories_saved": ["User likes tea"],
            },
        )
        self.assertEqual(
            app.conversation_history,
            [
                {"role": "user", "content": "I like tea"},
                {"role": "assistant", "content": "Tea sounds good."},
            ],
        )

    @patch("app.memory.retrieve", return_value=[])
    @patch("app.client.chat.completions.create")
    def test_empty_model_response_does_not_change_history(
        self, create_completion, _retrieve
    ):
        create_completion.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        )

        response = self.client.post("/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(app.conversation_history, [])


class MemoriesRouteTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    @patch("app.memory.collection.get")
    def test_escapes_stored_memories(self, get_memories):
        get_memories.return_value = {"documents": ["<script>alert(1)</script>"]}

        response = self.client.get("/memories")

        body = response.get_data(as_text=True)
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)


if __name__ == "__main__":
    unittest.main()
