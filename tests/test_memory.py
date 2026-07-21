import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import memory  # noqa: E402


class RelativeDateTests(unittest.TestCase):
    def test_resolves_tomorrow_from_system_recording_time(self):
        reference = datetime(2026, 7, 21, 23, 30, tzinfo=timezone(timedelta(hours=8)))

        text, dates = memory.resolve_relative_dates("\u7528\u6237\u660e\u5929\u8fd9\u4e2a\u65f6\u95f4\u5f00\u4f1a", reference)

        self.assertEqual(text, "\u7528\u6237\u660e\u5929\uff082026-07-22\uff09\u8fd9\u4e2a\u65f6\u95f4\u5f00\u4f1a")
        self.assertEqual(dates, ["2026-07-22"])

    def test_resolves_longer_chinese_relative_dates_first(self):
        reference = datetime(2026, 7, 21, 10, tzinfo=timezone.utc)

        text, dates = memory.resolve_relative_dates("\u5927\u540e\u5929\u548c\u540e\u5929\u90fd\u6709\u5b89\u6392", reference)

        self.assertEqual(text, "\u5927\u540e\u5929\uff082026-07-24\uff09\u548c\u540e\u5929\uff082026-07-23\uff09\u90fd\u6709\u5b89\u6392")
        self.assertEqual(dates, ["2026-07-24", "2026-07-23"])

    @patch("memory.collection.add")
    @patch("memory.collection.count", return_value=0)
    @patch("memory.client.embeddings.create")
    @patch("memory.client.chat.completions.create")
    @patch("memory._local_now")
    def test_temporal_message_is_stored_when_extractor_returns_nothing(
        self, local_now, create_completion, create_embedding, _count, add
    ):
        recorded_at = datetime(2026, 7, 21, 16, 45, tzinfo=timezone(timedelta(hours=8)))
        local_now.return_value = recorded_at
        create_completion.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="[]"))]
        )
        create_embedding.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])]
        )

        saved = memory.extract_and_store("\u6211\u660e\u5929\u4e0b\u53483\u70b9\u5f00\u4f1a", "\u597d\u7684")

        self.assertEqual(
            saved,
            ["User's time-sensitive note: \u6211\u660e\u5929\uff082026-07-22\uff09\u4e0b\u53483\u70b9\u5f00\u4f1a"],
        )
        metadata = add.call_args.kwargs["metadatas"][0]
        self.assertEqual(metadata["category"], "episodic")
        self.assertEqual(metadata["event_date"], "2026-07-22")

    @patch("memory.collection.add")
    @patch("memory.collection.count", return_value=0)
    @patch("memory.client.embeddings.create")
    @patch("memory.client.chat.completions.create")
    @patch("memory._local_now")
    def test_extracted_ephemeral_memory_stores_record_and_event_dates(
        self, local_now, create_completion, create_embedding, _count, add
    ):
        recorded_at = datetime(2026, 7, 21, 16, 45, tzinfo=timezone(timedelta(hours=8)))
        local_now.return_value = recorded_at
        create_completion.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '[{"text": "\u7528\u6237\u660e\u5929\u53bb\u4e0a\u6d77", "category": "episodic", "importance": 0.8}]'
            )))]
        )
        create_embedding.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])]
        )

        saved = memory.extract_and_store("\u6211\u660e\u5929\u53bb\u4e0a\u6d77", "\u4e00\u8def\u987a\u98ce")

        self.assertEqual(saved, ["\u7528\u6237\u660e\u5929\uff082026-07-22\uff09\u53bb\u4e0a\u6d77"])
        prompt = create_completion.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Current system datetime: 2026-07-21T16:45:00+08:00", prompt)
        metadata = add.call_args.kwargs["metadatas"][0]
        self.assertEqual(metadata["recorded_at"], "2026-07-21T16:45:00+08:00")
        self.assertEqual(metadata["event_date"], "2026-07-22")
        self.assertEqual(metadata["created_at"], recorded_at.timestamp())


if __name__ == "__main__":
    unittest.main()
