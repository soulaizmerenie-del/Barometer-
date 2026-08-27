"""Импорт выгрузки Telegram Desktop (Экспорт истории → JSON).

Самый быстрый путь получить историю чатов: ключи и вход не нужны, файл
выгружается из десктопного клиента и разбирается здесь.
"""

from __future__ import annotations

import html as html_mod
import json
import re
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


# --- Выгрузка в HTML -------------------------------------------------------
# Telegram Desktop по умолчанию предлагает именно HTML. Структура файла
# устойчивая: подряд идут блоки div.message, у первого сообщения серии есть
# from_name, у последующих (класс joined) его нет — отправитель наследуется.

_MESSAGE = re.compile(r'<div class="message ([^"]*)" id="message(-?\d+)">')
_STAMP = re.compile(r'<div class="pull_right date details" title="([^"]+)"')
_FROM = re.compile(r'<div class="from_name">\s*(.*?)\s*</div>', re.S)
_TEXT = re.compile(r'<div class="text">\s*(.*?)\s*</div>\s*</div>', re.S)
_REPLY = re.compile(r'GoToMessage\((\d+)\)')
_MEDIA = re.compile(r'media_(photo|voice_message|video_file|file|call|audio_file)')
_TAG = re.compile(r'<[^>]+>')
# Пересланное сообщение несёт своего автора и свою дату — брать нужно их,
# а не того, кто переслал, и не время пересылки.
_FWD = re.compile(r'<div class="forwarded body">(.*)', re.S)
_FWD_FROM = re.compile(r'<div class="from_name">(.*?)</div>', re.S)
_FWD_STAMP = re.compile(r'<span class="date details" title="([^"]+)"')


def _html_text(chunk: str) -> str:
    """Достаёт текст сообщения, сохраняя переносы строк."""
    found = _TEXT.search(chunk)
    if not found:
        return ""
    body = found.group(1)
    body = re.sub(r"<br\s*/?>", "\n", body)
    return html_mod.unescape(_TAG.sub("", body)).strip()


def _html_title(page: str) -> str:
    found = re.search(r'page_header.*?<div class="text bold">\s*(.*?)\s*</div>', page, re.S)
    return html_mod.unescape(_TAG.sub("", found.group(1)).strip()) if found else ""


def parse_html(path: Path, day: date | None = None, *, chats: tuple[Chat, ...] = CHATS) -> list[Message]:
    """Разбирает messages.html выгрузки Telegram Desktop.

    Многостраничные выгрузки (messages2.html и далее) передаются отдельными
    путями — каждая страница разбирается самостоятельно.
    """
    page = path.read_text(encoding="utf-8", errors="replace")
    title = _html_title(page)
    chat = _chat_for(title, chats)
    if chat is None:
        raise ValueError(
            f"{path.name}: чат «{title}» не входит в отслеживаемые. "
            "Добавьте название в barometer/config.py, если он нужен."
        )

    tz = ZoneInfo(TIMEZONE)
    out: list[Message] = []
    author = "неизвестно"
    bounds = [(m.start(), m.group(1), m.group(2)) for m in _MESSAGE.finditer(page)]

    for index, (start, classes, msg_id) in enumerate(bounds):
        end = bounds[index + 1][0] if index + 1 < len(bounds) else len(page)
        chunk = page[start:end]
        if "service" in classes:
            continue  # разделитель даты

        forwarded = _FWD.search(chunk)
        stamp_text = None

        if forwarded:
            # Автор и время оригинала, если они указаны в блоке пересылки.
            inner = _FWD_FROM.search(forwarded.group(1))
            if inner:
                block = inner.group(1)
                original = _FWD_STAMP.search(block)
                if original:
                    stamp_text = original.group(1)
                    block = block[: original.start()]
                name = html_mod.unescape(_TAG.sub("", block).strip())
                if name:
                    author = name
        else:
            found_from = _FROM.search(chunk)
            if found_from:
                author = html_mod.unescape(_TAG.sub("", found_from.group(1)).strip())

        if stamp_text is None:
            stamp = _STAMP.search(chunk)
            if not stamp:
                continue
            stamp_text = stamp.group(1)
        # Формат: "26.08.2026 10:14:34 UTC+01:00"
        when = datetime.strptime(stamp_text[:19], "%d.%m.%Y %H:%M:%S").replace(tzinfo=tz)
        if day is not None and when.date() != day:
            continue

        media = _MEDIA.search(chunk)
        text = _html_text(forwarded.group(1) if forwarded else chunk)
        if media and not text:
            # Содержимого нет, но факт важен: звонок, голосовое, фото.
            kind = {
                "call": "звонок", "voice_message": "голосовое сообщение",
                "photo": "фото", "video_file": "видео",
                "file": "файл", "audio_file": "аудио",
            }[media.group(1)]
            status = re.search(r'<div class="status details">\s*(.*?)\s*</div>', chunk, re.S)
            detail = html_mod.unescape(_TAG.sub("", status.group(1)).strip()) if status else ""
            text = f"[{kind}{': ' + detail if detail else ''}]"

        reply = _REPLY.search(chunk)
        out.append(
            Message(
                chat_key=chat.key,
                chat_title=chat.title,
                message_id=int(msg_id),
                at=when.strftime("%Y-%m-%d %H:%M"),
                author=author,
                text=text,
                reply_to=int(reply.group(1)) if reply else None,
                has_media=bool(media),
            )
        )

    out.sort(key=lambda m: (m.at, m.message_id))
    return out
