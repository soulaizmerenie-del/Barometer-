"""Сбор сообщений из рабочих чатов Telegram. Только чтение.

Клиент физически лишён методов отправки: все записывающие методы Telethon
заменены на исключение (см. _lock_read_only). Ничего написать в чат этот код
не может, даже при ошибке в вызывающей стороне.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CHATS, DIGESTS_DIR, TIMEZONE, Chat

# Всё, чем можно что-то изменить на стороне Telegram.
_FORBIDDEN = (
    "send_message", "send_file", "send_read_acknowledge", "forward_messages",
    "edit_message", "delete_messages", "pin_message", "unpin_message",
    "edit_permissions", "edit_admin", "kick_participant", "delete_dialog",
)


class WriteAttempted(RuntimeError):
    """Попытка записи в Telegram из режима только чтения."""


def _lock_read_only(client) -> None:
    for name in _FORBIDDEN:
        if not hasattr(client, name):
            continue

        def blocked(*_args, _name=name, **_kwargs):
            raise WriteAttempted(
                f"{_name}() запрещён: бот работает только на чтение. "
                "Писать в рабочие чаты можно лишь с явного разрешения владельца."
            )

        setattr(client, name, blocked)


@dataclass
class Message:
    """Сообщение чата в виде, пригодном для разбора задач."""

    chat_key: str
    chat_title: str
    message_id: int
    at: str
    author: str
    text: str
    reply_to: int | None = None
    has_media: bool = False


def day_bounds(day: date, tz_name: str = TIMEZONE) -> tuple[datetime, datetime]:
    """Границы суток отчёта в UTC-aware виде."""
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


async def collect(
    day: date,
    *,
    chats: tuple[Chat, ...] = CHATS,
    limit_per_chat: int = 500,
) -> list[Message]:
    """Читает сообщения трёх рабочих чатов за указанные сутки."""
    from telethon import TelegramClient  # импорт здесь: зависимость нужна только тут

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError(
            "Не заданы TELEGRAM_API_ID / TELEGRAM_API_HASH. "
            "Получите их на my.telegram.org и положите в .env (см. .env.example)."
        )
    session = os.environ.get("TELEGRAM_SESSION", "barometer")

    start, end = day_bounds(day)
    collected: list[Message] = []

    client = TelegramClient(session, int(api_id), api_hash)
    async with client:
        _lock_read_only(client)
        wanted = {}
        async for dialog in client.iter_dialogs():
            for chat in chats:
                if chat.key not in wanted and chat.matches(dialog.name or ""):
                    wanted[chat.key] = (chat, dialog.entity)

        missing = [c.title for c in chats if c.key not in wanted]
        if missing:
            raise RuntimeError(
                "Не найдены чаты: " + ", ".join(missing) +
                ". Проверьте названия в barometer/config.py — эмодзи и регистр не важны."
            )

        for chat, entity in wanted.values():
            async for msg in client.iter_messages(entity, offset_date=end, limit=limit_per_chat):
                if msg.date is None or msg.date < start:
                    break
                if msg.date >= end:
                    continue
                sender = await msg.get_sender()
                collected.append(
                    Message(
                        chat_key=chat.key,
                        chat_title=chat.title,
                        message_id=msg.id,
                        at=msg.date.astimezone(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M"),
                        author=_sender_name(sender),
                        text=(msg.message or "").strip(),
                        reply_to=msg.reply_to_msg_id,
                        has_media=msg.media is not None,
                    )
                )

    collected.sort(key=lambda m: (m.at, m.chat_key, m.message_id))
    return collected


def _sender_name(sender) -> str:
    if sender is None:
        return "неизвестно"
    for attr in ("title", "first_name"):
        value = getattr(sender, attr, None)
        if value:
            last = getattr(sender, "last_name", None)
            return f"{value} {last}".strip() if attr == "first_name" and last else value
    username = getattr(sender, "username", None)
    return f"@{username}" if username else "неизвестно"


def save(day: date, messages: list[Message], directory: Path = DIGESTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{day.isoformat()}.json"
    path.write_text(
        json.dumps(
            {"date": day.isoformat(), "messages": [asdict(m) for m in messages]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def load(day: date, directory: Path = DIGESTS_DIR) -> list[Message]:
    path = directory / f"{day.isoformat()}.json"
    if not path.exists():
        raise FileNotFoundError(f"Нет выгрузки {path}. Сначала `barometer collect`.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Message(**m) for m in raw.get("messages", [])]
