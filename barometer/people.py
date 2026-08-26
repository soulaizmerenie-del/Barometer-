"""Нормализация имён: в матрице, в чатах и в отчётах люди названы по-разному."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Person:
    """Сотрудник в каноническом виде, как он должен выглядеть в отчёте."""

    canonical: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    # Ник(и) в Telegram, если известны — заполняется по мере опознания.
    telegram: tuple[str, ...] = field(default_factory=tuple)
    outsource: bool = False


PEOPLE: tuple[Person, ...] = (
    Person(
        "Игорь Кожемяка",
        aliases=("КИ", "ИК", "И.Кожемяка", "И. Кожемяка", "Кожемяка", "Игорь"),
        telegram=("Игорь Кожемяка",),
    ),
    Person(
        "Максим Новоселов",
        aliases=(
            "М.Новоселов",
            "М. Новоселов",
            "Новоселов",
            "МН",
            "Максим",
            "М.Новосёлов",
            "Новосёлов",
        ),
    ),
    Person(
        "В. Баскаков",
        aliases=("В.Баскаков", "Баскаков", "Виталий Баскаков", "Vitalii Baskakov"),
        telegram=("Vitalii Baskakov",),
    ),
    Person(
        "В. Дранчук",
        aliases=("В.Дранчук", "Дранчук", "Виталий Дранчук", "Vitalii Дранчук"),
    ),
    Person("Беатрисс", aliases=("Беатрис", "Beatriss", "Беатрисc")),
    Person("Олег Педанов", aliases=("О.Педанов", "О. Педанов", "Педанов", "Олег")),
    Person("Кирилл Попов", aliases=("К.Попов", "К. Попов", "Попов")),
    Person(
        "С. Птицына (аутсорс)",
        aliases=("С.Птицына", "С.Птицинына", "Птицына", "Птицинына"),
        outsource=True,
    ),
    Person(
        "Сертифицированный инженер (аутсорс)",
        aliases=("сертифицированный инженер", "инженер (аутсорс)"),
        outsource=True,
    ),
    Person(
        "Монтажные бригады (аутсорс)",
        aliases=("монтажные бригады", "мг", "монтажная группа"),
        outsource=True,
    ),
    Person("Водитель (аутсорс)", aliases=("водитель",), outsource=True),
)

# "Виталий" без фамилии — это и Баскаков, и Дранчук. Не угадываем.
AMBIGUOUS = {"виталий", "vitalii", "витя"}


def _key(value: str) -> str:
    value = value.replace("ё", "е").lower()
    return re.sub(r"[^a-zа-я0-9]+", "", value)


_INDEX: dict[str, Person] = {}
for _person in PEOPLE:
    for _name in (_person.canonical, *_person.aliases, *_person.telegram):
        _INDEX.setdefault(_key(_name), _person)


class AmbiguousName(ValueError):
    """Имя не позволяет однозначно определить сотрудника."""


def resolve(name: str, *, strict: bool = False) -> str:
    """Приводит любое написание имени к каноническому.

    Неизвестное имя возвращается как есть — в чатах регулярно появляются
    подрядчики и клиенты, которых нет в матрице.
    """
    raw = name.strip().strip(",;")
    if not raw:
        return ""
    key = _key(raw)
    if key in AMBIGUOUS:
        if strict:
            raise AmbiguousName(
                f"{raw!r}: и Баскаков, и Дранчук — Виталий. Нужна фамилия."
            )
        return raw
    person = _INDEX.get(key)
    return person.canonical if person else raw


def resolve_list(names: str | list[str]) -> list[str]:
    """Разбирает строку матрицы вида 'КИ, М.Новоселов, В.Баскаков'."""
    if isinstance(names, str):
        parts = re.split(r"[,;/]|\bи\b", names)
    else:
        parts = list(names)
    out: list[str] = []
    for part in parts:
        person = resolve(part)
        if person and person not in out:
            out.append(person)
    return out


def is_known(name: str) -> bool:
    return _key(name) in _INDEX
