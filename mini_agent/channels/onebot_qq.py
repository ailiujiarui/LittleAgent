import json
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Set

from mini_agent.bus import MessageBus
from mini_agent.models import InboundMessage, OutboundMessage


_CQ_AT_PATTERN = re.compile(r"\[CQ:at,qq=([^\]]+)\]")


class OneBotQQChannel:
    def __init__(
        self,
        bot_id: str,
        bus: Optional[MessageBus] = None,
        allowed_private_users: Optional[Iterable[str]] = None,
        groups: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> None:
        self.bot_id = str(bot_id)
        self.bus = bus
        self._sockets = set()
        self._server = None
        self.allowed_private_users = _string_set(allowed_private_users)
        self.groups = {
            str(group_id): {
                "allow_from": _string_set(rule.get("allow_from", set())),
                "require_at": bool(rule.get("require_at", True)),
            }
            for group_id, rule in (groups or {}).items()
        }

    def parse_event(self, event: Mapping[str, Any]) -> Optional[InboundMessage]:
        if event.get("post_type") != "message":
            return None

        message_type = event.get("message_type")
        if message_type == "private":
            return self._parse_private_event(event)
        if message_type == "group":
            return self._parse_group_event(event)
        return None

    def build_send_payload(self, message: OutboundMessage) -> Dict[str, Any]:
        if message.channel != "qq":
            raise ValueError(f"unsupported channel: {message.channel}")

        if message.chat_id.startswith("gqq:"):
            return {
                "action": "send_group_msg",
                "params": {
                    "group_id": int(message.chat_id.removeprefix("gqq:")),
                    "message": message.text,
                },
            }
        return {
            "action": "send_private_msg",
            "params": {"user_id": int(message.chat_id), "message": message.text},
        }

    async def handle_event(self, event: Mapping[str, Any]) -> Optional[InboundMessage]:
        message = self.parse_event(event)
        if message is not None and self.bus is not None:
            await self.bus.publish_inbound(message)
        return message

    async def send_via_socket(self, socket: Any, message: OutboundMessage) -> None:
        await socket.send(json.dumps(self.build_send_payload(message), ensure_ascii=False))

    async def send(self, message: OutboundMessage) -> None:
        if not self._sockets:
            raise RuntimeError("OneBot socket is not connected")
        for socket in list(self._sockets):
            await self.send_via_socket(socket, message)

    async def start(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        try:
            import websockets
        except ModuleNotFoundError as exc:
            raise RuntimeError("websockets is required for OneBot QQ channel") from exc

        self._server = await websockets.serve(self._handle_socket, host, port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_socket(self, socket: Any) -> None:
        self._sockets.add(socket)
        try:
            async for raw in socket:
                await self.handle_event(json.loads(raw))
        finally:
            self._sockets.discard(socket)

    def _parse_private_event(self, event: Mapping[str, Any]) -> Optional[InboundMessage]:
        sender_id = str(event.get("user_id", ""))
        if self.allowed_private_users and sender_id not in self.allowed_private_users:
            return None

        return InboundMessage(
            channel="qq",
            chat_id=sender_id,
            sender_id=sender_id,
            text=_message_to_text(event.get("message")).strip(),
            message_id=_optional_str(event.get("message_id")),
            raw=dict(event),
            metadata={"chat_type": "private", "user_id": sender_id},
        )

    def _parse_group_event(self, event: Mapping[str, Any]) -> Optional[InboundMessage]:
        group_id = str(event.get("group_id", ""))
        rule = self.groups.get(group_id)
        if rule is None:
            return None

        sender_id = str(event.get("user_id", ""))
        allow_from: Set[str] = rule["allow_from"]
        if allow_from and sender_id not in allow_from:
            return None

        message = event.get("message")
        has_bot_at = _has_bot_at(message, self.bot_id)
        if rule["require_at"] and not has_bot_at:
            return None

        return InboundMessage(
            channel="qq",
            chat_id=f"gqq:{group_id}",
            sender_id=sender_id,
            text=_message_to_text(message, strip_at=True).strip(),
            message_id=_optional_str(event.get("message_id")),
            raw=dict(event),
            metadata={
                "chat_type": "group",
                "group_id": group_id,
                "sender_id": sender_id,
            },
        )


def _string_set(values: Optional[Iterable[Any]]) -> Set[str]:
    return {str(value) for value in (values or set())}


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _has_bot_at(message: Any, bot_id: str) -> bool:
    if isinstance(message, list):
        for segment in message:
            if segment.get("type") != "at":
                continue
            if str(segment.get("data", {}).get("qq")) == bot_id:
                return True
        return False

    if isinstance(message, str):
        return any(match.group(1) == bot_id for match in _CQ_AT_PATTERN.finditer(message))
    return False


def _message_to_text(message: Any, strip_at: bool = False) -> str:
    if isinstance(message, list):
        parts = []
        for segment in message:
            segment_type = segment.get("type")
            if strip_at and segment_type == "at":
                continue
            if segment_type == "text":
                parts.append(str(segment.get("data", {}).get("text", "")))
        return "".join(parts)

    if isinstance(message, str):
        if strip_at:
            return _CQ_AT_PATTERN.sub("", message)
        return message
    return ""
