from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    channel: str
    chat_id: str
    sender_id: str
    text: str
    message_id: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def session_key(self) -> str:
        return f"{self.channel}:{self.chat_id}"


class OutboundMessage(BaseModel):
    channel: str
    chat_id: str
    text: str
    reply_to: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
