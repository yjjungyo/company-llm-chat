"""실제 회사 API 접근 없이 로컬 기록 기능 검증."""
import tempfile
import unittest
from pathlib import Path

from chat_store import init_db, new_chat, add_message, get_messages, list_chats, delete_chat


class TestStore(unittest.TestCase):
    def test_chat_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "store.db"
            init_db(db)
            chat_id = new_chat(db)
            add_message(chat_id, "user", "안녕", db)
            add_message(chat_id, "assistant", "반갑습니다", db)
            self.assertEqual([x["content"] for x in get_messages(chat_id, db)], ["안녕", "반갑습니다"])
            self.assertEqual(list_chats(db)[0]["title"], "안녕")
            delete_chat(chat_id, db)
            self.assertEqual(get_messages(chat_id, db), [])
            self.assertEqual(list_chats(db), [])


if __name__ == "__main__":
    unittest.main()
