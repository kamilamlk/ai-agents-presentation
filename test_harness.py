"""
Тесты харнесса. Ни одного обращения к API, ни одного потраченного токена.

    python3 test_harness.py

Модель подменена заглушкой, которая отдаёт заранее записанные ответы.
"""

import copy
from types import SimpleNamespace as NS

from example_harness import check, run


# ── Поддельная модель ────────────────────────────────────────────────────────

def text_block(t):
    return NS(type="text", text=t)


def tool_block(name, **kwargs):
    return NS(type="tool_use", id="toolu_fake", name=name, input=kwargs)


def reply(stop_reason, *blocks):
    return NS(stop_reason=stop_reason, content=list(blocks))


def answer(times):
    body = '{"times": ' + str(list(times)).replace("'", '"') + "}"
    return reply("end_turn", text_block(f"```json\n{body}\n```"))


class FakeClient:
    """Отдаёт заготовленные ответы по порядку и запоминает, о чём её спрашивали."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []
        self.messages = self

    def create(self, **kw):
        # Снимок обязателен: messages мутируется по ходу цикла, и без копии
        # все записи в self.sent укажут на одно финальное состояние.
        self.sent.append({**kw, "messages": copy.deepcopy(kw["messages"])})
        return self.replies.pop(0)


def quiet(*a, **kw):
    pass


# ── Проверка: чистая функция, модель не нужна вообще ────────────────────────

def test_check_пропускает_возрастающие():
    assert check(["06:15", "06:47", "07:20"]) is None


def test_check_ловит_шаг_назад():
    assert "23:40" in check(["23:05", "23:40", "00:15"])


def test_check_ловит_одинаковые():
    assert check(["06:15", "06:15"]) is not None


def test_check_переживает_один_элемент():
    assert check(["06:15"]) is None


# ── Цикл: поддельная модель, ветвление проверяется целиком ──────────────────

def test_инструмент_вызван_и_результат_вернулся():
    c = FakeClient(
        reply("tool_use", tool_block("read_timetable", city="Ярославль")),
        answer(["06:15", "06:47"]),
    )
    run(c, log=quiet)

    second = c.sent[1]["messages"][-1]
    assert second["role"] == "user"
    assert second["content"][0]["type"] == "tool_result"
    assert "5А" in second["content"][0]["content"]


def test_повтор_после_провала_проверки():
    c = FakeClient(
        answer(["23:05", "23:40", "00:15"]),   # модель ошиблась
        answer(["23:05", "23:40", "24:15"]),   # исправилась
    )
    assert run(c, log=quiet) == ["23:05", "23:40", "24:15"]
    assert len(c.sent) == 2
    assert "Не годится" in c.sent[1]["messages"][-1]["content"]


def test_хороший_ответ_принят_с_первого_раза():
    c = FakeClient(answer(["06:15", "06:47"]))
    assert run(c, log=quiet) == ["06:15", "06:47"]
    assert len(c.sent) == 1


def test_цикл_не_бесконечный():
    c = FakeClient(*[answer(["09:00", "08:00"]) for _ in range(6)])
    try:
        run(c, log=quiet)
    except RuntimeError:
        return
    raise AssertionError("цикл должен был сдаться")


def test_обрезанный_ответ_не_считается_успехом():
    c = FakeClient(reply("max_tokens", text_block("```json")))
    try:
        run(c, log=quiet)
    except RuntimeError as e:
        assert "max_tokens" in str(e)
        return
    raise AssertionError("обрезанный ответ должен падать, а не приниматься")


# ── Запуск ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok    {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"ПАДАЕТ {t.__name__}: {e}")
    print(f"\n{len(tests) - failed} из {len(tests)} прошли")
