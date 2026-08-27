"""Рендер задач и отчётов в формате, принятом в ZFOS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import TASKS_DIR

# Статусы и их подпись в отчёте.
STATUSES: dict[str, str] = {
    "done": "готово ✅",
    "completed": "выполнено ✅",
    "in_progress": "в процессе",
    "not_started": "не начато",
    "blocked": "заблокировано ⛔",
    "overdue": "просрочено ⚠️",
    "cancelled": "снято",
    # Отдельный статус вместо молчаливого переноса вчерашнего: если задачи в
    # выгрузке нет, отчёт обязан это показать, а не додумывать.
    "no_data": "нет данных в выгрузке",
}


@dataclass
class Evidence:
    """Ссылка на сообщение, по которому выставлен статус."""

    chat: str
    message_id: int | None = None
    author: str = ""
    at: str = ""
    text: str = ""


@dataclass
class Task:
    """Пункт задачника / отчёта."""

    title: str
    responsible: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    executors: list[str] = field(default_factory=list)
    status: str = "in_progress"
    status_note: str = ""
    report_title: str = ""
    function: str = ""
    division: str = ""
    evidence: list[Evidence] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "Task":
        data = dict(raw)
        data["evidence"] = [Evidence(**e) for e in data.get("evidence", [])]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def status_label(self) -> str:
        label = STATUSES.get(self.status, self.status)
        return f"{label}, {self.status_note}" if self.status_note else label


@dataclass
class Day:
    """Набор задач на конкретную дату."""

    date: date
    tasks: list[Task] = field(default_factory=list)

    @classmethod
    def load(cls, day: date, directory: Path = TASKS_DIR) -> "Day":
        path = directory / f"{day.isoformat()}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Нет файла задач {path}. Создайте его или соберите дайджест командой "
                f"`barometer digest --date {day.isoformat()}`."
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(date=day, tasks=[Task.from_dict(t) for t in raw.get("tasks", [])])

    def save(self, directory: Path = TASKS_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.date.isoformat()}.json"
        payload = {
            "date": self.date.isoformat(),
            "tasks": [_task_to_dict(task) for task in self.tasks],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path


def _task_to_dict(task: Task) -> dict:
    return {
        "title": task.title,
        "report_title": task.report_title,
        "status": task.status,
        "status_note": task.status_note,
        "responsible": task.responsible,
        "participants": task.participants,
        "executors": task.executors,
        "division": task.division,
        "function": task.function,
        "evidence": [vars(e) for e in task.evidence],
    }


def _people_block(label_one: str, label_many: str, names: list[str]) -> list[str]:
    if not names:
        return []
    label = label_one if len(names) == 1 else label_many
    return [f"{label}:", ", ".join(names)]


def render_tasks(day: Day) -> str:
    """Формат 'Задачи на DD.MM'."""
    lines = [f"Задачи на {day.date:%d.%m}:", ""]
    for index, task in enumerate(day.tasks, start=1):
        lines.append(f"{index}. {task.title}")
        lines += _people_block("Ответственный", "Ответственные", task.responsible)
        lines += _people_block("Участник", "Участники", task.participants)
        lines += _people_block("Исполнитель", "Исполнители", task.executors)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_report(day: Day) -> str:
    """Формат 'Отчет на DD.MM' — тот же список плюс статус в заголовке пункта."""
    lines = [f"Отчет на {day.date:%d.%m}:", ""]
    for index, task in enumerate(day.tasks, start=1):
        title = task.report_title or task.title
        lines.append(f"{index}. {title} - {task.status_label()}")
        lines += _people_block("Ответственный", "Ответственные", task.responsible)
        lines += _people_block("Участник", "Участники", task.participants)
        lines += _people_block("Исполнитель", "Исполнители", task.executors)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_evidence(day: Day) -> str:
    """Приложение к отчёту: на каком сообщении основан каждый статус."""
    lines = [f"Основания статусов на {day.date:%d.%m}:", ""]
    for index, task in enumerate(day.tasks, start=1):
        lines.append(f"{index}. {task.report_title or task.title} — {task.status_label()}")
        if not task.evidence:
            lines.append("   нет подтверждения в чатах — статус проставлен вручную")
        for item in task.evidence:
            head = f"   [{item.chat}] {item.at} {item.author}".rstrip()
            lines.append(head)
            if item.text:
                lines.append(f"      {item.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
