"""Дайджест: из сырых сообщений — материал, по которому пишется отчёт."""

from __future__ import annotations

import re
from datetime import date

from . import matrix
from . import text as text_mod
from .collect import Message
from .config import CHATS
from .report import Day

# Слова, по которым сообщение похоже на изменение статуса задачи.
STATUS_MARKERS: dict[str, tuple[str, ...]] = {
    "done": ("готово", "сделал", "сделано", "выполнил", "выполнено", "закрыл", "отгруз",
             "доставил", "привез", "оплатил", "отправил", "подписал", "смонтировал",
             "заверш", "закончил", "закончен", "нашли", "нашел", "нашёл", "договорились",
             "получили", "установил", "подключил", "согласовано", "решили", "решен",
             "решён", "принято", "оформил"),
    "in_progress": ("в процессе", "делаю", "работаю", "начал", "занимаюсь", "уточня",
                    "жду ответ", "ждем", "ждём", "в работе", "согласов", "готовлю",
                    "собираю", "считаю"),
    "blocked": ("не могу", "нет ответа", "заблок", "проблема", "отказ", "сорвал",
                "не получилось", "нет в наличии", "задерж", "не успел", "не отвечает",
                "застрял", "сломал"),
    "planned": ("завтра", "к понедельник", "на след", "перенес", "запланир",
                "к концу недели", "на этой неделе"),
}

_QUESTION = re.compile(r"\?\s*$")


def classify(text: str) -> list[str]:
    """Какие статусные маркеры встречаются в сообщении."""
    lowered = text.lower()
    return [
        status
        for status, markers in STATUS_MARKERS.items()
        if any(marker in lowered for marker in markers)
    ]


def _mentions(task_title: str, text: str) -> int:
    """Сколько значимых слов задачи встретилось в сообщении."""
    return text_mod.relevance(task_title, text)


def build(day: date, messages: list[Message], previous: Day | None = None) -> str:
    """Собирает markdown-дайджест за сутки.

    Дайджест — вход для составления отчёта: он не решает за человека, какой
    статус у задачи, а показывает переписку и подсказки матрицы.
    """
    divisions = matrix.load()
    lines = [f"# Дайджест рабочих чатов за {day:%d.%m.%Y}", ""]
    lines.append(f"Всего: {plural_messages(len(messages))}")
    lines.append("")

    if previous and previous.tasks:
        lines.append("## Задачи прошлого дня и относящиеся к ним сообщения")
        lines.append("")
        for index, task in enumerate(previous.tasks, start=1):
            lines.append(f"### {index}. {task.title}")
            lines.append(
                f"Ответственный: {', '.join(task.responsible) or '—'} · "
                f"Участники: {', '.join(task.participants) or '—'} · "
                f"Исполнители: {', '.join(task.executors) or '—'}"
            )
            related = sorted(
                ((_mentions(task.title, m.text), m) for m in messages if m.text),
                key=lambda pair: pair[0],
                reverse=True,
            )
            hits = [m for score, m in related if score >= 2][:6]
            if not hits:
                lines.append("_Упоминаний в чатах за сутки не найдено._")
            for msg in hits:
                marks = ", ".join(classify(msg.text)) or "—"
                lines.append(
                    f"- [{msg.chat_title} #{msg.message_id}] {msg.at} **{msg.author}** "
                    f"(маркеры: {marks}): {_short(msg.text)}"
                )
            lines.append("")

    lines.append("## Переписка по чатам")
    lines.append("")
    for chat in CHATS:
        chat_messages = [m for m in messages if m.chat_key == chat.key]
        lines.append(f"### {chat.title} ({plural_messages(len(chat_messages))})")
        if chat.note:
            lines.append(f"_{chat.note}_")
        lines.append("")
        for msg in chat_messages:
            if not msg.text:
                lines.append(f"- {msg.at} **{msg.author}**: _(вложение без текста)_")
                continue
            marks = classify(msg.text)
            flag = f" `{'/'.join(marks)}`" if marks else ""
            question = " `вопрос`" if _QUESTION.search(msg.text) else ""
            lines.append(
                f"- #{msg.message_id} {msg.at} **{msg.author}**{flag}{question}: {_short(msg.text)}"
            )
        lines.append("")

    lines.append("## Кандидаты в новые задачи")
    lines.append("")
    candidates = [m for m in messages if m.text and _looks_like_task(m.text)]
    if not candidates:
        lines.append("_Не найдено._")
    for msg in candidates:
        lines.append(f"- [{msg.chat_title} #{msg.message_id}] **{msg.author}**: {_short(msg.text)}")
        for score, fn in matrix.suggest(msg.text, divisions, limit=2):
            if score < 0.2:
                continue
            lines.append(
                f"  - матрица ({score:.0%}): {fn.division} / {fn.name} — "
                f"О: {', '.join(fn.responsible) or '—'}; "
                f"У: {', '.join(fn.participants) or '—'}; "
                f"И: {', '.join(fn.informed) or '—'}"
            )
    lines.append("")
    return "\n".join(lines)


_TASK_HINT = re.compile(
    r"\b(над[оы]|нужно|прошу|сделай|подготов|организ|закаж|уточни|проверь|"
    r"выясни|найди|отправ|свяжись|запрос)", re.IGNORECASE
)


def _looks_like_task(text: str) -> bool:
    return bool(_TASK_HINT.search(text))


def plural_messages(count: int) -> str:
    """Согласование числительного: 1 сообщение / 2 сообщения / 5 сообщений."""
    tail = count % 100
    if 11 <= tail <= 14:
        word = "сообщений"
    elif count % 10 == 1:
        word = "сообщение"
    elif count % 10 in (2, 3, 4):
        word = "сообщения"
    else:
        word = "сообщений"
    return f"{count} {word}"


def _short(text: str, limit: int = 400) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
