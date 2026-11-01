"""단일 사용자 로컬 채팅 기록 보관(SQLite).

중요: 로그인/권한 분리가 없는 개인용 앱입니다. 다중 사용자 서버로 공개하지 마세요.
"""

from contextlib import contextmanager
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DB_PATH = Path(__file__).resolve().parent / "data" / "chats.sqlite3"


@contextmanager
def connect(db_path: Path = DB_PATH):
    """DB 폴더 생성 후 연결. 외래키 제약 활성화 및 사용 후 안전한 close 보장."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH):
    with connect(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
        """)


def now():
    return datetime.now(timezone.utc).isoformat()


def new_chat(db_path: Path = DB_PATH):
    chat_id = str(uuid4())
    timestamp = now()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO chats VALUES (?, ?, ?, ?)",
            (chat_id, "새 채팅", timestamp, timestamp),
        )
    return chat_id


def list_chats(db_path: Path = DB_PATH):
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id, title, updated_at FROM chats ORDER BY updated_at DESC"
        )]


def get_messages(chat_id: str, db_path: Path = DB_PATH):
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id", (chat_id,)
        )]


def add_message(chat_id: str, role: str, content: str, db_path: Path = DB_PATH):
    if role not in ("user", "assistant"):
        raise ValueError("허용되지 않은 메시지 역할")
    timestamp = now()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, timestamp),
        )
        conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (timestamp, chat_id))
        if role == "user":
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='user'", (chat_id,)
            ).fetchone()[0]
            if count == 1:
                title = " ".join(content.split())[:35] or "새 채팅"
                conn.execute("UPDATE chats SET title=? WHERE id=?", (title, chat_id))


def delete_chat(chat_id: str, db_path: Path = DB_PATH):
    with connect(db_path) as conn:
        conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
