"""Вход в Telegram в два шага, без интерактивного ввода.

Штатный Telethon спрашивает телефон и код через stdin. Здесь вход разбит на
две команды, чтобы код подтверждения можно было передать отдельным вызовом:

    barometer login request --phone +38267123456
    barometer login code --code 12345 [--password ...]

Файл сессии (`barometer.session`) — это полноценный доступ к учётной записи:
он позволяет читать переписку без повторного ввода кода. Он в `.gitignore`,
но обращаться с ним нужно как с паролем. Выйти отовсюду можно из самого
Telegram: Настройки → Устройства → завершить сеанс.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STATE_PATH = Path(".login_state.json")


class LoginError(RuntimeError):
    """Вход не удался."""


def _credentials() -> tuple[int, str, str]:
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise LoginError(
            "Не заданы TELEGRAM_API_ID / TELEGRAM_API_HASH. Возьмите их на "
            "my.telegram.org → API development tools и положите в .env."
        )
    session = os.environ.get("TELEGRAM_SESSION", "barometer")
    return int(api_id), api_hash, session


def _client():
    from telethon import TelegramClient

    api_id, api_hash, session = _credentials()
    return TelegramClient(session, api_id, api_hash)


async def request(phone: str) -> str:
    """Шаг 1: запросить код подтверждения на номер."""
    client = _client()
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            return f"Вход уже выполнен: {me.first_name} (+{me.phone}). Код не нужен."
        sent = await client.send_code_request(phone)
        STATE_PATH.write_text(
            json.dumps({"phone": phone, "hash": sent.phone_code_hash}), encoding="utf-8"
        )
        return (
            f"Код отправлен на {phone} (тип: {type(sent.type).__name__}).\n"
            "Пришлите его командой: barometer login code --code XXXXX"
        )
    finally:
        await client.disconnect()


async def sign_in(code: str, password: str | None = None) -> str:
    """Шаг 2: подтвердить код (и пароль двухфакторной защиты, если он есть)."""
    from telethon.errors import (
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        SessionPasswordNeededError,
    )

    if not STATE_PATH.exists():
        raise LoginError("Сначала выполните `barometer login request --phone ...`.")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    client = _client()
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=state["phone"], code=code, phone_code_hash=state["hash"]
            )
        except SessionPasswordNeededError:
            if not password:
                raise LoginError(
                    "Включена двухфакторная защита. Повторите с паролем: "
                    "barometer login code --code XXXXX --password ВАШ_ПАРОЛЬ"
                ) from None
            await client.sign_in(password=password)
        except PhoneCodeInvalidError:
            raise LoginError("Неверный код. Проверьте и повторите.") from None
        except PhoneCodeExpiredError:
            raise LoginError(
                "Код просрочен. Запросите новый: barometer login request --phone ..."
            ) from None

        me = await client.get_me()
        STATE_PATH.unlink(missing_ok=True)
        return f"Вход выполнен: {me.first_name} {me.last_name or ''} (@{me.username})".strip()
    finally:
        await client.disconnect()


async def status() -> str:
    """Проверить,жива ли сессия, и какие из трёх чатов видны."""
    from .config import CHATS

    client = _client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return "Вход не выполнен. Начните с `barometer login request --phone ...`."
        me = await client.get_me()
        lines = [f"Вход выполнен: {me.first_name} (@{me.username})", ""]
        found = {}
        async for dialog in client.iter_dialogs():
            for chat in CHATS:
                if chat.key not in found and chat.matches(dialog.name or ""):
                    found[chat.key] = dialog.name
        for chat in CHATS:
            if chat.key in found:
                lines.append(f"✓ {chat.title} — найден как «{found[chat.key]}»")
            else:
                lines.append(f"✗ {chat.title} — не найден среди ваших диалогов")
        return "\n".join(lines)
    finally:
        await client.disconnect()
