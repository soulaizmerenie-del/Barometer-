"""Проверки: рендер отчёта, разбор матрицы, запрет записи в Telegram."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from barometer import matrix, people  # noqa: E402
from barometer.collect import WriteAttempted, _lock_read_only  # noqa: E402
from barometer.config import CHATS, chat_by_key  # noqa: E402
from barometer.report import Day, render_report, render_tasks  # noqa: E402


def test_people_resolve():
    assert people.resolve("КИ") == "Игорь Кожемяка"
    assert people.resolve("М. Новоселов") == "Максим Новоселов"
    assert people.resolve("В.Дранчук") == "В. Дранчук"
    assert people.resolve("Vitalii Baskakov") == "В. Баскаков"
    # Одно имя "Виталий" носят двое — не угадываем.
    assert people.resolve("Виталий") == "Виталий"
    assert people.resolve_list("КИ, В.Баскаков") == ["Игорь Кожемяка", "В. Баскаков"]


def test_matrix_parsed():
    divisions = matrix.load()
    assert len(divisions) == 10
    assert len(matrix.functions(divisions)) == 91
    engineering = next(d for d in divisions if d.name.startswith("Инженерно"))
    assert engineering.owner == ["Максим Новоселов"]


def test_matrix_suggest_delivery():
    top = matrix.suggest("Доставка оборудования Нехаду")[0][1]
    assert top.name == "доставка оборудования клиентам"
    assert top.responsible == ["В. Баскаков"]


def test_chat_matching_ignores_emoji_and_case():
    main = chat_by_key("main")
    assert main.matches("ZFOS♻️☀️Основной Чат")
    assert chat_by_key("clientele").matches("ZFOS♻️🛎 CLIENTELE")
    assert len(CHATS) == 3


def test_report_matches_reference_format():
    day = Day.load(date(2026, 8, 25))
    report = render_report(day)
    assert report.startswith("Отчет на 25.08:")
    assert "1. Оценка инвентаря - готово ✅" in report
    assert "2. Подготовка кп - в процессе, готовность к 26.08" in report
    assert "5. Доставка оборудования Нехаду - выполнено ✅" in report
    assert render_tasks(day).startswith("Задачи на 25.08:")
    # Пункт без участников не печатает пустой блок.
    assert "Участник:\n\nИсполнитель" not in report


def test_client_cannot_write():
    class FakeClient:
        def send_message(self, *_a, **_k):
            raise AssertionError("сообщение не должно быть отправлено")

        def delete_messages(self, *_a, **_k):
            raise AssertionError("сообщение не должно быть удалено")

    client = FakeClient()
    _lock_read_only(client)
    for call in (client.send_message, client.delete_messages):
        try:
            call("chat", "текст")
        except WriteAttempted:
            continue
        raise AssertionError("запись не была заблокирована")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print(f"ok   {name}")
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {error}")
    raise SystemExit(1 if failures else 0)
