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

    def test_rejects_invalid_message_batch(self):
        response = self.client.post("/chat", json={"messages": ["hello", " "]})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Messages cannot be empty"})

    @patch("app.memory.retrieve", return_value=[])
    @patch("app.client.chat.completions.create")
    def test_successful_chat(self, create_completion, _retrieve):
        create_completion.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"replies": ["Tea sounds good."]}'
                    )
                )
            ]
        )

        response = self.client.post(
            "/chat", json={"message": " I like tea ", "lang": "zh"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "response": "Tea sounds good.",
                "responses": ["Tea sounds good."],
            },
        )
        self.assertEqual(
            app.conversation_history,
            [
                {"role": "user", "content": "I like tea"},
                {"role": "assistant", "content": "Tea sounds good."},
            ],
        )
        sent_messages = create_completion.call_args.kwargs["messages"]
        self.assertIn("Simplified Chinese", sent_messages[0]["content"])
        response_format = create_completion.call_args.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertEqual(
            response_format["json_schema"]["schema"]["properties"]["replies"]["maxItems"],
            10,
        )

    @patch("app.memory.retrieve", return_value=[])
    @patch("app.client.chat.completions.create")
    def test_combines_a_batch_of_short_messages(self, create_completion, retrieve):
        create_completion.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"replies": ['
                            '"Today should be mild.", '
                            '"Tomorrow looks a little warmer."]}'
                        )
                    )
                )
            ]
        )

        response = self.client.post(
            "/chat",
            json={"messages": [" How is the weather today? ", "And tomorrow?"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["responses"],
            ["Today should be mild.", "Tomorrow looks a little warmer."],
        )
        retrieve.assert_called_once_with("How is the weather today?\nAnd tomorrow?")
        self.assertEqual(
            app.conversation_history[0],
            {
                "role": "user",
                "content": "How is the weather today?\nAnd tomorrow?",
            },
        )
        self.assertEqual(
            app.conversation_history[1],
            {
                "role": "assistant",
                "content": "Today should be mild.\nTomorrow looks a little warmer.",
            },
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

    @patch("app.memory.retrieve", return_value=[])
    @patch("app.client.chat.completions.create")
    def test_invalid_structured_response_does_not_change_history(
        self, create_completion, _retrieve
    ):
        create_completion.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
        )

        response = self.client.post("/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(app.conversation_history, [])


class RememberRouteTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    @patch("app.memory.extract_and_store", return_value=["User likes tea"])
    def test_stores_memory_after_the_visible_reply(self, extract):
        response = self.client.post(
            "/remember",
            json={
                "user_message": " I like tea ",
                "assistant_message": " Tea sounds good. ",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(), {"memories_saved": ["User likes tea"]}
        )
        extract.assert_called_once_with("I like tea", "Tea sounds good.")

    def test_rejects_empty_memory_input(self):
        response = self.client.post(
            "/remember",
            json={"user_message": " ", "assistant_message": "hello"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "User message must be a non-empty string"},
        )


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

    def test_demo_displays_long_and_short_term_memories(self):
        response = self.client.get("/memories?demo=1")

        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("长期记忆", body)
        self.assertIn("短期记忆", body)
        self.assertIn("用户的名字是小明", body)
        self.assertIn("示例数据", body)

    @patch("app.memory.collection.get")
    def test_memory_page_uses_selected_language(self, get_memories):
        get_memories.return_value = {"documents": [], "metadatas": []}
        expected_copy = {
            "en": ('lang="en"', "Long-term memory", "Back to chat"),
            "zh": ('lang="zh-CN"', "长期记忆", "返回聊天"),
            "de": ('lang="de"', "Langzeitgedächtnis", "Zurück zum Chat"),
        }

        for lang, phrases in expected_copy.items():
            with self.subTest(lang=lang):
                response = self.client.get(f"/memories?lang={lang}")
                body = response.get_data(as_text=True)

                self.assertEqual(response.status_code, 200)
                for phrase in phrases:
                    self.assertIn(phrase, body)
                self.assertIn(f"/memories?demo=1&amp;lang={lang}", body)

    def test_demo_memories_use_selected_language(self):
        response = self.client.get("/memories?demo=1&lang=de")

        body = response.get_data(as_text=True)
        self.assertIn("Der Benutzer heißt Alex", body)
        self.assertIn("Beispieldaten", body)
        self.assertIn("/memories?lang=de", body)


class IndexRouteTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    def test_chat_page_has_language_settings(self):
        response = self.client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="settings-button"', body)
        self.assertIn('id="settings-overlay"', body)
        self.assertIn('data-settings-lang="en"', body)
        self.assertIn('data-settings-lang="zh"', body)
        self.assertIn('data-settings-lang="de"', body)
        self.assertIn("function waitUntilUserStopsTyping()", body)


if __name__ == "__main__":
    unittest.main()
