"""Конфигурация: чаты, пути, таймзона."""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TASKS_DIR = DATA_DIR / "tasks"
DIGESTS_DIR = DATA_DIR / "digests"
MATRIX_CSV = DATA_DIR / "matrix.csv"

MATRIX_SHEET_ID = "1ukWZEN0DclITlPBjiJ3qoyH0Akqi23RmcvWW_zneaGQ"
MATRIX_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{MATRIX_SHEET_ID}/export?format=csv"
)

# Часовой пояс, в котором считаются "сутки" отчёта (Черногория).
TIMEZONE = os.getenv("BAROMETER_TZ", "Europe/Podgorica")


@dataclass(frozen=True)
class Chat:
    """Рабочий чат, из которого собираются данные."""

    key: str
    title: str
    # Варианты названия в Telegram: эмодзи и регистр у групп плавают.
    aliases: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""
    # Личный диалог: бот в него попасть не может, для сбора ботом непригоден.
    group: bool = True

    def matches(self, title: str) -> bool:
        norm = _norm(title)
        return any(_norm(a) in norm or norm in _norm(a) for a in (self.title, *self.aliases))


def _norm(value: str) -> str:
    """Сводит название к сопоставимому виду.

    Помимо эмодзи, пробелов и регистра снимается юникодное оформление:
    участники пишут название жирными математическими буквами (𝐙𝐅𝐎𝐒), и без
    NFKC такое название не совпадёт с обычным ZFOS.
    """
    folded = unicodedata.normalize("NFKC", value).lower()
    return "".join(ch for ch in folded if ch.isalnum())


# Три чата со скриншота, обведённые зелёным.
CHATS: tuple[Chat, ...] = (
    Chat(
        key="tasks",
        title="Задачи ZFOS",
        aliases=("Задачи ZFOS", "ЗАДАЧИ ZFOS"),
        note="Постановка задач: основной источник пунктов отчёта.",
    ),
    Chat(
        key="clientele",
        title="ZFOS CLIENTELE",
        aliases=("ZFOS♻️🛎 CLIENTELE", "ZFOS CLIENTELE", "CLIENTELE", "Клиенты"),
        note="Клиенты, КП, заявки, поставки под конкретные объекты.",
    ),
    Chat(
        key="dm_igor",
        title="Личная переписка с И. Кожемякой",
        aliases=("Игорь Кожемяка",),
        note="Личный диалог: часть решений принимается здесь, а не в группах.",
        group=False,
    ),
    Chat(
        key="relay",
        title="клауд работа",
        aliases=("клауд работа",),
        note="Пересылки из рабочих чатов. Исходный чат при пересылке теряется.",
        group=False,
    ),
    Chat(
        key="main",
        title="ZFOS Основной Чат",
        aliases=("ZFOS♻️☀️Основной Чат", "ZFOS Основной Чат", "Основной Чат"),
        note="Общий рабочий чат: статусы, монтажи, логистика, импорт.",
    ),
)


GROUP_CHATS: tuple[Chat, ...] = tuple(c for c in CHATS if c.group)


def chat_by_key(key: str) -> Chat:
    for chat in CHATS:
        if chat.key == key:
            return chat
    raise KeyError(f"Неизвестный чат: {key!r}. Доступны: {[c.key for c in CHATS]}")
