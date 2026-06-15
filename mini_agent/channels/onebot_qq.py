import asyncio
import json
import re
import uuid
from urllib.parse import parse_qs, urlsplit
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional, Set

from mini_agent.bus import MessageBus
from mini_agent.models import InboundMessage, OutboundMessage


_CQ_AT_PATTERN = re.compile(r"\[CQ:at,qq=([^\]]+)\]")
EventEmitter = Callable[[str, Dict[str, Any]], Awaitable[None]]


class OneBotQQChannel:
    def __init__(
        self,
        bot_id: str,
        bus: Optional[MessageBus] = None,
        allowed_private_users: Optional[Iterable[str]] = None,
        groups: Optional[Mapping[str, Mapping[str, Any]]] = None,
        logger: Optional[Callable[[str], None]] = None,
        event_emitter: Optional[EventEmitter] = None,
        path: str = "/onebot/v11/ws",
        access_token: Optional[str] = None,
    ) -> None:
        self.bot_id = str(bot_id)
        self.bus = bus
        self.logger = logger or (lambda message: None)
        self.event_emitter = event_emitter
        self.path = path
        self.access_token = access_token
        self._sockets = set()
        self._server = None
        self._pending_echo: Dict[str, asyncio.Future] = {}
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

    def build_send_payload(
        self,
        message: OutboundMessage,
        echo: Optional[str] = None,
    ) -> Dict[str, Any]:
        if message.channel != "qq":
            raise ValueError(f"unsupported channel: {message.channel}")

        echo = echo or str(uuid.uuid4())
        if message.chat_id.startswith("gqq:"):
            return {
                "action": "send_group_msg",
                "echo": echo,
                "params": {
                    "group_id": int(message.chat_id.removeprefix("gqq:")),
                    "message": message.text,
                },
            }
        return {
            "action": "send_private_msg",
            "echo": echo,
            "params": {"user_id": int(message.chat_id), "message": message.text},
        }

    async def handle_event(self, event: Mapping[str, Any]) -> Optional[InboundMessage]:
        if "echo" in event:
            echo = str(event.get("echo"))
            future = self._pending_echo.pop(echo, None)
            if future is not None and not future.done():
                future.set_result(dict(event))
            return None

        if self.event_emitter is not None:
            group_event = self._group_plugin_event(event)
            if group_event is not None:
                await self.event_emitter("group_message", group_event)

        message = self.parse_event(event)
        if message is not None and self.bus is not None:
            self.logger(
                f"OneBot inbound {message.metadata.get('chat_type', message.channel)} "
                f"{message.chat_id}: {message.text}"
            )
            await self.bus.publish_inbound(message)
        elif event.get("post_type") == "message":
            self.logger(
                "OneBot message ignored: "
                f"type={event.get('message_type')} "
                f"user_id={event.get('user_id')} "
                f"group_id={event.get('group_id')}"
            )
        return message

    async def send_via_socket(
        self,
        socket: Any,
        message: OutboundMessage,
        wait_response: bool = False,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        payload = self.build_send_payload(message)
        echo = str(payload["echo"])
        future: Optional[asyncio.Future] = None

        if wait_response:
            future = asyncio.get_running_loop().create_future()
            self._pending_echo[echo] = future

        try:
            await socket.send(json.dumps(payload, ensure_ascii=False))
            if future is None:
                return None
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending_echo.pop(echo, None)

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
        if not await self._validate_socket(socket):
            return

        self._sockets.add(socket)
        address = getattr(socket, "remote_address", "unknown")
        self.logger(f"OneBot socket connected: {address}")
        try:
            async for raw in socket:
                await self.handle_event(json.loads(raw))
        finally:
            self._sockets.discard(socket)
            self.logger(f"OneBot socket disconnected: {address}")

    async def _validate_socket(self, socket: Any) -> bool:
        raw_path = _socket_raw_path(socket)
        if raw_path is None:
            return True

        parsed = urlsplit(raw_path)
        if parsed.path != self.path:
            self.logger(f"OneBot socket rejected: invalid path {parsed.path}")
            await _close_socket(socket, "invalid OneBot path")
            return False

        if self.access_token and _socket_access_token(socket, parsed.query) != self.access_token:
            self.logger("OneBot socket rejected: invalid access token")
            await _close_socket(socket, "invalid OneBot access token")
            return False
        return True

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
        group_event = self._group_plugin_event(event)
        if group_event is None:
            return None

        group_id = group_event["group_id"]
        if self.groups[group_id]["require_at"] and not group_event["mentioned_bot"]:
            return None

        return InboundMessage(
            channel="qq",
            chat_id=f"gqq:{group_id}",
            sender_id=group_event["sender_id"],
            text=group_event["text"],
            message_id=group_event["message_id"],
            raw=dict(event),
            metadata={
                "chat_type": "group",
                "group_id": group_id,
                "sender_id": group_event["sender_id"],
            },
        )

    def _group_plugin_event(self, event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        if event.get("post_type") != "message" or event.get("message_type") != "group":
            return None

        group_id = str(event.get("group_id", ""))
        rule = self.groups.get(group_id)
        if rule is None:
            return None

        sender_id = str(event.get("user_id", ""))
        allow_from: Set[str] = rule["allow_from"]
        if allow_from and sender_id not in allow_from:
            return None

        message = event.get("message")
        sender = event.get("sender") or {}
        return {
            "group_id": group_id,
            "sender_id": sender_id,
            "sender_name": str(sender.get("card") or sender.get("nickname") or ""),
            "text": _message_to_text(message, strip_at=True).strip(),
            "message_id": _optional_str(event.get("message_id")),
            "timestamp": event.get("time"),
            "mentioned_bot": _has_bot_at(message, self.bot_id),
        }


def _string_set(values: Optional[Iterable[Any]]) -> Set[str]:
    return {str(value) for value in (values or set())}


async def _close_socket(socket: Any, reason: str) -> None:
    close = getattr(socket, "close", None)
    if close is not None:
        await close(code=1008, reason=reason)


def _socket_raw_path(socket: Any) -> Optional[str]:
    request = getattr(socket, "request", None)
    path = getattr(request, "path", None)
    if path is None:
        path = getattr(socket, "path", None)
    if path is None:
        return None
    return str(path)


def _socket_access_token(socket: Any, query: str) -> Optional[str]:
    values = parse_qs(query).get("access_token")
    if values:
        return values[0]

    request = getattr(socket, "request", None)
    headers = getattr(request, "headers", None)
    if headers is None:
        headers = getattr(socket, "request_headers", None)
    if headers is None:
        return None

    authorization = _header_get(headers, "Authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return _header_get(headers, "access_token") or _header_get(headers, "x-access-token")


def _header_get(headers: Any, name: str) -> Optional[str]:
    getter = getattr(headers, "get", None)
    if getter is not None:
        value = getter(name)
        if value is None:
            value = getter(name.lower())
        if value is not None:
            return str(value)
    return None


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
