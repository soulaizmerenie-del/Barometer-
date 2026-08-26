"""Матрица зон ответственности ZFOS: загрузка, разбор, подсказка ролей."""

from __future__ import annotations

import csv
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import people
from .config import MATRIX_CSV, MATRIX_CSV_URL


@dataclass
class Function:
    """Строка матрицы: функция и её роли О / У / И."""

    division: str
    name: str
    responsible: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    informed: list[str] = field(default_factory=list)


@dataclass
class Division:
    """Подразделение: владелец, функции, рабочая группа, ЦКП."""

    name: str
    owner: list[str] = field(default_factory=list)
    working_group: list[str] = field(default_factory=list)
    functions: list[Function] = field(default_factory=list)
    ckp: str = ""


_BULLET = re.compile(r"^[•\-•\s]+")
_CKP = re.compile(r"^ЦКП\s*:\s*", re.IGNORECASE)


def fetch(dest: Path = MATRIX_CSV, *, url: str = MATRIX_CSV_URL) -> Path:
    """Скачивает актуальную матрицу из Google Sheets в CSV."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        dest.write_bytes(response.read())
    return dest


def load(path: Path = MATRIX_CSV) -> list[Division]:
    """Разбирает CSV матрицы в список подразделений."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    divisions: list[Division] = []
    current: Division | None = None

    for row in rows[1:]:  # первая строка — заголовки колонок
        cells = [cell.strip() for cell in (row + [""] * 5)[:5]]
        title, resp, part, inf, group = cells
        if not any(cells):
            continue
        if _CKP.match(title):
            if current is not None:
                current.ckp = _CKP.sub("", title).strip()
            continue
        if title.startswith("•") or (current is not None and _looks_like_function(title)):
            if current is None:
                continue
            current.functions.append(
                Function(
                    division=current.name,
                    name=_BULLET.sub("", title).strip(),
                    responsible=people.resolve_list(resp),
                    participants=people.resolve_list(part),
                    informed=people.resolve_list(inf),
                )
            )
            if group:
                current.working_group = people.resolve_list(group)
            continue

        # Строка без маркера и с заполненным "О" — это заголовок подразделения.
        current = Division(
            name=title,
            owner=people.resolve_list(resp),
            working_group=people.resolve_list(group),
        )
        divisions.append(current)

    return divisions


def _looks_like_function(title: str) -> bool:
    """Часть строк в таблице потеряла маркер '•' — опознаём их по регистру."""
    return bool(title) and title[:1].islower()


def functions(divisions: list[Division] | None = None) -> list[Function]:
    divisions = divisions if divisions is not None else load()
    return [fn for division in divisions for fn in division.functions]


_STOP = {
    "для","под","при","над","из","от","до","на","в","и","с","по","о","об","к","у",
    "the","of","а","же","что","как","это","все","актуальные","актуальный","дальнейших",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[а-яa-zё]{4,}", text.lower().replace("ё", "е"))
    # Грубое усечение окончаний: точной морфологии тут не нужно.
    return {w[:6] for w in words if w not in _STOP}


def suggest(task_text: str, divisions: list[Division] | None = None, *, limit: int = 3) -> list[tuple[float, Function]]:
    """Подбирает функции матрицы, наиболее близкие к тексту задачи.

    Возвращает пары (оценка совпадения, функция), отсортированные по убыванию.
    Оценка — доля совпавших слов функции; ниже 0.2 совпадение считать нельзя.
    """
    task_tokens = _tokens(task_text)
    if not task_tokens:
        return []
    scored: list[tuple[float, Function]] = []
    for fn in functions(divisions):
        fn_tokens = _tokens(fn.name)
        if not fn_tokens:
            continue
        overlap = task_tokens & fn_tokens
        if not overlap:
            continue
        scored.append((len(overlap) / len(fn_tokens), fn))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:limit]
