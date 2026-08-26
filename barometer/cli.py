"""CLI: barometer collect | digest | report | tasks | matrix | whoami."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta

from . import collect as collect_mod
from . import digest as digest_mod
from . import matrix as matrix_mod
from .config import CHATS, DIGESTS_DIR, TASKS_DIR
from .report import Day, render_evidence, render_report, render_tasks


def _parse_date(value: str | None) -> date:
    if not value or value == "today":
        return date.today()
    if value == "yesterday":
        return date.today() - timedelta(days=1)
    return datetime.strptime(value, "%Y-%m-%d").date()


def cmd_collect(args: argparse.Namespace) -> int:
    day = _parse_date(args.date)
    messages = asyncio.run(collect_mod.collect(day, limit_per_chat=args.limit))
    path = collect_mod.save(day, messages)
    print(f"Собрано {len(messages)} сообщений за {day:%d.%m.%Y} → {path}")
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    day = _parse_date(args.date)
    messages = collect_mod.load(day)
    previous = None
    try:
        previous = Day.load(day - timedelta(days=1))
    except FileNotFoundError:
        pass
    text = digest_mod.build(day, messages, previous)
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGESTS_DIR / f"{day.isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Дайджест → {path}")
    if args.print:
        print()
        print(text)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    day = _parse_date(args.date)
    data = Day.load(day)
    print(render_report(data))
    if args.evidence:
        print()
        print(render_evidence(data))
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    day = _parse_date(args.date)
    print(render_tasks(Day.load(day)))
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    if args.update:
        path = matrix_mod.fetch()
        print(f"Матрица обновлена → {path}")
    if args.suggest:
        divisions = matrix_mod.load()
        for score, fn in matrix_mod.suggest(args.suggest, divisions):
            print(
                f"{score:.0%}  {fn.division} / {fn.name}\n"
                f"      Ответственный: {', '.join(fn.responsible) or '—'}\n"
                f"      Участники: {', '.join(fn.participants) or '—'}\n"
                f"      Информируемые: {', '.join(fn.informed) or '—'}"
            )
        return 0
    if not args.update:
        for division in matrix_mod.load():
            print(f"{division.name} — О: {', '.join(division.owner) or '—'}")
            for fn in division.functions:
                print(f"   • {fn.name} — О: {', '.join(fn.responsible) or '—'}")
    return 0


def cmd_chats(_args: argparse.Namespace) -> int:
    for chat in CHATS:
        print(f"{chat.key:10} {chat.title}\n           {chat.note}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="barometer",
        description="Мониторинг рабочих чатов ZFOS и отчёты по матрице ответственности.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="прочитать сообщения трёх чатов за сутки")
    p.add_argument("--date", default="today", help="YYYY-MM-DD | today | yesterday")
    p.add_argument("--limit", type=int, default=500, help="максимум сообщений на чат")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("digest", help="собрать дайджест из выгрузки")
    p.add_argument("--date", default="today")
    p.add_argument("--print", action="store_true", help="вывести дайджест в консоль")
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("report", help="отчёт по задачам дня")
    p.add_argument("--date", default="today")
    p.add_argument("--evidence", action="store_true", help="приложить основания статусов")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("tasks", help="список задач дня")
    p.add_argument("--date", default="today")
    p.set_defaults(func=cmd_tasks)

    p = sub.add_parser("matrix", help="матрица ответственности")
    p.add_argument("--update", action="store_true", help="перекачать из Google Sheets")
    p.add_argument("--suggest", metavar="ТЕКСТ", help="подобрать функцию под задачу")
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("chats", help="какие чаты отслеживаются")
    p.set_defaults(func=cmd_chats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
