"""Черновик задачника: статусы предлагаются по переписке, человек подтверждает.

Полностью автоматическим этот шаг быть не может — «сделаю завтра» и «сделал»
отличает смысл, а не ключевые слова. Поэтому каждый вывод сопровождается
сообщением-основанием и пометкой уверенности: спорное видно сразу, остальное
достаточно бегло просмотреть.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from . import matrix
from . import text as text_mod
from .collect import Message
from .digest import classify
from .report import Day, Evidence, Task

# Маркер из сообщения → статус задачи.
MARKER_TO_STATUS = {
    "done": "done",
    "in_progress": "in_progress",
    "blocked": "blocked",
    "planned": "in_progress",
}

# Насколько уверенно можно считать, что сообщение относится к задаче.
STRONG_MATCH = 3
WEAK_MATCH = 2


def _relevance(task_title: str, text: str) -> int:
    return text_mod.relevance(task_title, text)


def _evidence(message: Message) -> Evidence:
    return Evidence(
        chat=message.chat_title,
        message_id=message.message_id,
        author=message.author,
        at=message.at,
        text=message.text[:300],
    )


def _status_from(messages: list[tuple[int, Message]]) -> tuple[str, str, list[Evidence]]:
    """Определяет статус по самому позднему сообщению с внятным маркером."""
    marked = [
        (score, msg, classify(msg.text))
        for score, msg in messages
        if classify(msg.text)
    ]
    if not marked:
        return "", "", [_evidence(m) for _, m in messages[:3]]

    marked.sort(key=lambda item: item[1].at)
    score, message, markers = marked[-1]
    # blocked важнее прочего: незакрытая помеха должна быть видна в отчёте.
    marker = "blocked" if "blocked" in markers else markers[0]
    note = "готовность уточнить" if marker == "planned" else ""
    return MARKER_TO_STATUS[marker], note, [_evidence(m) for _, m in messages[:3]]


def _carry_over(previous: Day | None) -> list[Task]:
    """Переносит незакрытые задачи прошлого дня."""
    if previous is None:
        return []
    carried = []
    for task in previous.tasks:
        if task.status in ("done", "completed", "cancelled"):
            continue
        carried.append(
            Task(
                title=task.title,
                report_title=task.report_title,
                responsible=list(task.responsible),
                participants=list(task.participants),
                executors=list(task.executors),
                division=task.division,
                function=task.function,
                status=task.status,
            )
        )
    return carried


_TASK_HINT = re.compile(
    r"\b(над[оы]|нужно|прошу|сделай|подготов|организ|закаж|уточни|проверь|"
    r"выясни|найди|отправ|свяжись|запрос)", re.IGNORECASE
)


def _new_tasks(messages: list[Message], existing: list[Task]) -> list[Task]:
    """Сообщения, похожие на постановку задачи и не покрытые текущим списком."""
    divisions = matrix.load()
    found: list[Task] = []
    for message in messages:
        if not message.text or not _TASK_HINT.search(message.text):
            continue
        # Уже есть похожая задача — не плодим дубль.
        if any(_relevance(t.title, message.text) >= WEAK_MATCH for t in existing + found):
            continue
        suggestions = matrix.suggest(message.text, divisions, limit=1)
        division = function = ""
        responsible: list[str] = []
        participants: list[str] = []
        executors: list[str] = []
        if suggestions and suggestions[0][0] >= 0.34:
            _, fn = suggestions[0]
            division, function = fn.division, fn.name
            responsible, participants, executors = (
                list(fn.responsible), list(fn.participants), list(fn.informed)
            )
        found.append(
            Task(
                title=message.text[:120],
                status="not_started",
                division=division,
                function=function,
                responsible=responsible,
                participants=participants,
                executors=executors,
                evidence=[_evidence(message)],
            )
        )
    return found


def build(day: date, messages: list[Message], previous: Day | None = None) -> tuple[Day, list[str]]:
    """Собирает черновик задачника на день и список того, что требует проверки."""
    tasks = _carry_over(previous)
    review: list[str] = []

    for index, task in enumerate(tasks, start=1):
        related = sorted(
            ((_relevance(task.title, m.text), m) for m in messages if m.text),
            key=lambda pair: pair[0],
            reverse=True,
        )
        hits = [(score, m) for score, m in related if score >= WEAK_MATCH][:5]
        if not hits:
            task.evidence = []
            review.append(
                f"{index}. {task.title} — в чатах не упоминалась, статус оставлен "
                f"прежним ({task.status})"
            )
            continue

        status, note, evidence = _status_from(hits)
        task.evidence = evidence
        if not status:
            review.append(f"{index}. {task.title} — упоминается, но статус не следует из текста")
            continue
        task.status = status
        task.status_note = note
        if max(score for score, _ in hits) < STRONG_MATCH:
            review.append(
                f"{index}. {task.title} — статус «{status}» выведен по слабому совпадению, проверьте"
            )
        if status == "blocked":
            review.append(f"{index}. {task.title} — помеха, нужно решение")

    fresh = _new_tasks(messages, tasks)
    for task in fresh:
        review.append(f"НОВАЯ: {task.title} — проверьте формулировку и роли")
    tasks.extend(fresh)

    return Day(date=day, tasks=tasks), review


def previous_day(day: date) -> Day | None:
    try:
        return Day.load(day - timedelta(days=1))
    except FileNotFoundError:
        return None
