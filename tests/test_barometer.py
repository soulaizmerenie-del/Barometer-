"""Проверки: рендер отчёта, разбор матрицы, запрет записи в Telegram."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from barometer import import_export, matrix, people  # noqa: E402
from barometer import bot_watch  # noqa: E402
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


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "export_sample.json"


def test_import_export_one_day():
    messages = import_export.parse(FIXTURE, date(2026, 8, 25))
    assert len(messages) == 3
    chats = {m.chat_key for m in messages}
    assert chats == {"tasks", "clientele", "main"}
    # Личные заметки в отслеживаемые чаты не входят.
    assert all("не должно попасть" not in m.text for m in messages)


def test_import_export_flattens_formatting():
    messages = import_export.parse(FIXTURE, date(2026, 8, 25))
    task = next(m for m in messages if m.chat_key == "tasks")
    assert task.text == "Нужно найти поставщика для креплений панелей до конца недели"
    # Служебное сообщение (invite_members) пропущено.
    assert task.message_id == 102


def test_import_export_keeps_media_and_replies():
    messages = import_export.parse(FIXTURE, date(2026, 8, 25))
    photo = next(m for m in messages if m.chat_key == "main")
    assert photo.has_media is True
    reply = next(m for m in messages if m.chat_key == "clientele")
    assert reply.reply_to == 329


def test_import_export_all_days():
    messages = import_export.parse(FIXTURE)
    assert {m.at[:10] for m in messages} == {"2026-08-25", "2026-08-26"}


def _stub_bot(monkey: dict):
    """Подменяет вызовы Bot API заранее заданными ответами."""

    def fake_call(_token, method, **_params):
        return monkey[method]

    return fake_call


def test_bot_check_reports_privacy_mode(capture=None):
    import os

    original_call = bot_watch._call
    os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
    try:
        bot_watch._call = _stub_bot({
            "getMe": {"username": "zfos_bot", "first_name": "ZFOS",
                      "can_join_groups": True, "can_read_all_group_messages": False},
            "getUpdates": [],
        })
        # Privacy mode включён + ни одного чата не видно = 1 + 3 замечания.
        assert bot_watch.check() == 4
    finally:
        bot_watch._call = original_call
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_bot_check_passes_when_all_three_chats_seen():
    import os

    original_call = bot_watch._call
    os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
    updates = [
        {"update_id": i, "message": {"message_id": i, "date": 0,
         "chat": {"id": -100 - i, "title": title}}}
        for i, title in enumerate(
            ("Задачи ZFOS", "ZFOS♻️🛎 CLIENTELE", "ZFOS♻️☀️Основной Чат")
        )
    ]
    try:
        bot_watch._call = _stub_bot({
            "getMe": {"username": "zfos_bot", "first_name": "ZFOS",
                      "can_join_groups": True, "can_read_all_group_messages": True},
            "getUpdates": updates,
        })
        assert bot_watch.check() == 0
    finally:
        bot_watch._call = original_call
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_bot_message_conversion():
    update = {"update_id": 1, "message": {
        "message_id": 77, "date": 1787000000,
        "from": {"first_name": "Максим", "last_name": "Новоселов"},
        "chat": {"id": -1001, "title": "ZFOS♻️☀️Основной Чат"},
        "text": "Доставка Нехаду выполнена",
        "photo": [{"file_id": "x"}],
    }}
    message = bot_watch._to_message(update, chat_by_key("main"))
    assert message.author == "Максим Новоселов"
    assert message.chat_key == "main"
    assert message.has_media is True
    assert message.text == "Доставка Нехаду выполнена"


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
