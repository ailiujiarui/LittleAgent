import sqlite3
from pathlib import Path

from mini_agent.db.migrations import apply_migrations
from mini_agent.models import InboundMessage


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        apply_migrations(self.db_path)

    def ensure_session(self, message: InboundMessage) -> str:
        session_id = message.session_key
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert into sessions (id, channel, chat_id)
                values (?, ?, ?)
                on conflict(id) do update set
                    channel = excluded.channel,
                    chat_id = excluded.chat_id,
                    updated_at = current_timestamp
                """,
                (session_id, message.channel, message.chat_id),
            )
            conn.commit()
        return session_id


class MessageStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        apply_migrations(self.db_path)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert into messages (session_id, role, content)
                values (?, ?, ?)
                """,
                (session_id, role, content),
            )
            conn.commit()

    def list_messages(self, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                """
                select role, content
                from messages
                where session_id = ?
                order by id
                """,
                (session_id,),
            ).fetchall()
