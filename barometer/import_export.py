"""Импорт выгрузки Telegram Desktop (Экспорт истории → JSON).

Самый быстрый путь получить историю чатов: ключи и вход не нужны, файл
выгружается из десктопного клиента и разбирается здесь.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .collect import Message
from .config import CHATS, TIMEZONE, Chat


def _flatten(text) -> str:
    """Поле text — это строка либо список кусков (ссылки, упоминания, код)."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for part in text:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        return "".join(parts)
    return ""


def _chat_for(title: str, chats: tuple[Chat, ...]) -> Chat | None:
    for chat in chats:
        if chat.matches(title):
            return chat
    return None


def _messages_of(chat_blob: dict, chat: Chat, day: date | None) -> list[Message]:
    tz = ZoneInfo(TIMEZONE)
    out: list[Message] = []
    for raw in chat_blob.get("messages", []):
        if raw.get("type") != "message":
            continue  # сервисные события: вход в группу, смена фото и т.п.
        stamp = raw.get("date")
        if not stamp:
            continue
        when = datetime.fromisoformat(stamp)
        if when.tzinfo is None:
            when = when.replace(tzinfo=tz)
        local = when.astimezone(tz)
        if day is not None and local.date() != day:
            continue
        out.append(
            Message(
                chat_key=chat.key,
                chat_title=chat.title,
                message_id=int(raw.get("id", 0)),
                at=local.strftime("%Y-%m-%d %H:%M"),
                author=(raw.get("from") or "неизвестно"),
                text=_flatten(raw.get("text", "")).strip(),
                reply_to=raw.get("reply_to_message_id"),
                has_media=bool(raw.get("photo") or raw.get("file") or raw.get("media_type")),
            )
        )
    return out


def parse(path: Path, day: date | None = None, *, chats: tuple[Chat, ...] = CHATS) -> list[Message]:
    """Разбирает result.json выгрузки.

    Поддерживает оба формата: выгрузку одного чата и общую выгрузку со
    списком чатов. Чаты, не входящие в отслеживаемые три, пропускаются.
    """
    blob = json.loads(path.read_text(encoding="utf-8"))

    if "chats" in blob:
        blobs = blob["chats"].get("list", [])
    elif "messages" in blob:
        blobs = [blob]
    else:
        raise ValueError(
            f"{path} не похож на выгрузку Telegram: нет ни 'chats', ни 'messages'."
        )

    collected: list[Message] = []
    skipped: list[str] = []
    for chat_blob in blobs:
        title = chat_blob.get("name") or ""
        chat = _chat_for(title, chats)
        if chat is None:
            if title:
                skipped.append(title)
            continue
        collected.extend(_messages_of(chat_blob, chat, day))

    if not collected and skipped:
        raise ValueError(
            "В выгрузке нет ни одного из отслеживаемых чатов. Найдены: "
            + ", ".join(sorted(set(skipped))[:10])
            + ". Поправьте названия в barometer/config.py."
        )

    collected.sort(key=lambda m: (m.at, m.chat_key, m.message_id))
    return collected
