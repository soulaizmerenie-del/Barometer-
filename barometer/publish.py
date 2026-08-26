"""Доставка собранного в репозиторий, откуда его читает ассистент.

Дайджест — это рабочая переписка: клиенты, цены, поставщики, личные
сообщения коллег. Поэтому публикация намеренно требует явного разрешения в
.env и отказывается работать молча.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path

from .config import DIGESTS_DIR, TASKS_DIR


class PublishRefused(RuntimeError):
    """Публикация не разрешена настройками."""


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=Path.cwd()
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _guard() -> None:
    if os.environ.get("BAROMETER_ALLOW_PUBLISH") != "1":
        raise PublishRefused(
            "Публикация выключена. В репозиторий поедет рабочая переписка —\n"
            "  сначала убедитесь, что репозиторий приватный:\n"
            "    GitHub → Settings → General → Danger Zone → Change visibility\n"
            "  затем разрешите публикацию, добавив в .env:\n"
            "    BAROMETER_ALLOW_PUBLISH=1"
        )


def publish(day: date, *, branch: str | None = None) -> str:
    """Коммитит дайджест и задачник за день и отправляет в origin."""
    _guard()

    branch = branch or os.environ.get("BAROMETER_BRANCH") or _git("rev-parse", "--abbrev-ref", "HEAD")
    paths = [
        p for p in (
            DIGESTS_DIR / f"{day.isoformat()}.json",
            DIGESTS_DIR / f"{day.isoformat()}.md",
            TASKS_DIR / f"{day.isoformat()}.json",
        ) if p.exists()
    ]
    if not paths:
        raise RuntimeError(f"Нечего публиковать за {day:%d.%m.%Y}: файлы не найдены.")

    _git("add", *[str(p) for p in paths])
    if not _git("status", "--porcelain", "--", *[str(p) for p in paths]):
        return f"Изменений за {day:%d.%m.%Y} нет, публиковать нечего."

    _git("commit", "-m", f"Данные чатов за {day:%d.%m.%Y}")
    _git("push", "-u", "origin", branch)
    return (
        f"Опубликовано за {day:%d.%m.%Y}: {', '.join(p.name for p in paths)}\n"
        f"Ветка {branch}. Ассистент увидит их при следующем обращении."
    )
