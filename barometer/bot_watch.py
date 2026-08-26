"""Живой сбор через Telegram Bot API. Нужен только токен бота.

В отличие от чтения под своей учётной записью, тут не требуется ни api_id,
ни номер телефона, ни код подтверждения. Плата за это — бот не видит историю:
Bot API отдаёт только сообщения, пришедшие после его добавления в группу и
после запуска этого наблюдателя.

Условия работы в группах:
  1. бот добавлен во все три чата;
  2. у BotFather отключён privacy mode (/setprivacy → Disable), иначе бот
     видит только команды и ответы на свои сообщения;
  3. наблюдатель запущен и не останавливается — пропущенное за время простоя
     Telegram хранит примерно сутки, дальше сообщения теряются безвозвратно.

Отправлять этот модуль ничего не умеет: используется единственный метод
getUpdates, методов записи здесь нет.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .collect import Message, load, save
from .config import CHATS, DIGESTS_DIR, TIMEZONE, Chat
from .digest import plural_messages

API = "https://api.telegram.org/bot{token}/{method}"
ALLOWED_UPDATES = ["message", "edited_message", "channel_post"]


def _call(token: str, method: str, **params) -> dict:
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in params.items()}
    ).encode()
    with urllib.request.urlopen(url, data=data, timeout=90) as response:
        payload = json.loads(response.read())
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram вернул ошибку: {payload.get('description')}")
    return payload["result"]


def _chat_for(title: str, chats: tuple[Chat, ...]) -> Chat | None:
    for chat in chats:
        if chat.matches(title or ""):
            return chat
    return None


def _to_message(update: dict, chat: Chat) -> Message | None:
    body = update.get("message") or update.get("edited_message") or update.get("channel_post")
    if not body:
        return None
    sender = body.get("from") or {}
    author = " ".join(
        filter(None, (sender.get("first_name"), sender.get("last_name")))
    ) or sender.get("username") or (body.get("sender_chat") or {}).get("title") or "неизвестно"
    when = datetime.fromtimestamp(body.get("date", 0), tz=ZoneInfo(TIMEZONE))
    return Message(
        chat_key=chat.key,
        chat_title=chat.title,
        message_id=int(body.get("message_id", 0)),
        at=when.strftime("%Y-%m-%d %H:%M"),
        author=author,
        text=(body.get("text") or body.get("caption") or "").strip(),
        reply_to=(body.get("reply_to_message") or {}).get("message_id"),
        has_media=any(k in body for k in ("photo", "document", "video", "voice", "audio")),
    )


def _merge(day: date, fresh: list[Message], directory: Path) -> int:
    """Дописывает новые сообщения к выгрузке дня, не плодя дубликаты."""
    try:
        existing = load(day, directory)
    except FileNotFoundError:
        existing = []
    seen = {(m.chat_key, m.message_id) for m in existing}
    added = [m for m in fresh if (m.chat_key, m.message_id) not in seen]
    if not added:
        return 0
    merged = sorted(existing + added, key=lambda m: (m.at, m.chat_key, m.message_id))
    save(day, merged, directory)
    return len(added)


def watch(
    *,
    chats: tuple[Chat, ...] = CHATS,
    directory: Path = DIGESTS_DIR,
    timeout: int = 60,
    rounds: int | None = None,
) -> None:
    """Слушает обновления и раскладывает сообщения по файлам суток.

    rounds=None — слушать бесконечно; число — сделать столько опросов
    (удобно для разовой выемки накопившегося и для тестов).
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Не задан TELEGRAM_BOT_TOKEN. Создайте бота у @BotFather, отключите "
            "privacy mode, добавьте его в три рабочих чата и положите токен в .env."
        )

    me = _call(token, "getMe")
    print(f"Наблюдатель запущен под ботом @{me.get('username')} (только чтение)")

    offset = 0
    completed = 0
    while rounds is None or completed < rounds:
        try:
            updates = _call(
                token, "getUpdates", offset=offset, timeout=timeout,
                allowed_updates=ALLOWED_UPDATES,
            )
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"Сеть недоступна ({error}), повтор.")
            completed += 1
            continue

        by_day: dict[date, list[Message]] = {}
        for update in updates:
            offset = max(offset, update.get("update_id", 0) + 1)
            body = update.get("message") or update.get("edited_message") or update.get("channel_post") or {}
            chat = _chat_for((body.get("chat") or {}).get("title", ""), chats)
            if chat is None:
                continue  # чужой чат или личка — не наше дело
            message = _to_message(update, chat)
            if message is None:
                continue
            day = datetime.strptime(message.at, "%Y-%m-%d %H:%M").date()
            by_day.setdefault(day, []).append(message)

        for day, messages in by_day.items():
            added = _merge(day, messages, directory)
            if added:
                print(f"{day:%d.%m}: +{plural_messages(added)}")

        completed += 1
