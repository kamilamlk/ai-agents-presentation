"""
Самый маленький агент, который вообще возможен.
Один инструмент, один вопрос, четыре хода по сети.

Запуск:
    pip3 install anthropic
    source ./anthropic-env.sh on
    python3 example_tool_loop.py

Доступ подхватывается из окружения сам, кода менять не надо. SDK разрешает
креды по порядку: ANTHROPIC_API_KEY, потом ANTHROPIC_AUTH_TOKEN, потом профиль
`ant auth login`. Первый найденный выигрывает.

  - прямой ключ Anthropic  -> ANTHROPIC_API_KEY (уходит заголовком x-api-key)
  - корпоративный шлюз     -> ANTHROPIC_AUTH_TOKEN (уходит как Authorization:
                              Bearer) ПЛЮС обязательно ANTHROPIC_BASE_URL,
                              иначе запрос уйдёт на api.anthropic.com и упадёт

Через шлюз может отличаться список доступных моделей. Проверить:
    python3 -c "import anthropic; [print(m.id) for m in anthropic.Anthropic().models.list()]"
Если claude-opus-5 в списке нет, подставьте ниже тот id, который есть.

Что показать залу в этом файле:
  1. Модель никогда не видит TIMETABLES. Она видит TOOLS: имя, описание, схему.
  2. Строка `output = read_timetable(**block.input)` — единственное место,
     где что-то реально происходит. Её выполняет ваш код, не модель.
  3. `range(5)` — это и есть «харнесс владеет остановкой».

После запуска рядом появится wire.json: обычный отформатированный JSON, массив
сообщений в порядке обмена. Открывается любым редактором, читать глазами.
Файл перезаписывается на каждом ходу, так что он валиден даже если прогон упал.

Диагностика самого HTTP (метод, URL, статус, request_id, ретраи) включается
переменной окружения, тела ответа она не покажет:

    ANTHROPIC_LOG=debug python3 example_tool_loop.py
"""

import json
import pathlib

import anthropic

client = anthropic.Anthropic()


# ── Лог провода: всё, что ушло и пришло, построчным JSON в wire.jsonl ────────
#
# Логируем ТОЛЬКО тела. Заголовки не трогаем: там живёт токен, и ему не место
# ни в файле, ни на проекторе. Направления названы так же, как на схеме B+.

WIRE = pathlib.Path("wire.json")
_exchange: list = []


def wire(direction: str, payload: object) -> None:
    def encode(o: object) -> object:
        return o.model_dump(mode="json") if hasattr(o, "model_dump") else str(o)

    # Снимок делаем сразу: payload держит ссылку на список messages, который
    # дальше по циклу продолжает расти. Без round-trip в лог попала бы не та
    # переписка, что ушла на этом ходу, а её будущее состояние.
    snapshot = json.loads(json.dumps({"direction": direction, "payload": payload}, default=encode))

    _exchange.append(snapshot)
    WIRE.write_text(json.dumps(_exchange, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Ваши данные. Модель их не увидит никогда. ────────────────────────────────

TIMETABLES = {
    "Ярославль": "5А: 06:15, 06:47, 07:20, 07:53 | 21: 05:58, 06:30, 07:02",
    "Кострома": "3: 06:05, 06:40, 07:15 | 11: 06:22, 07:00",
}


def read_timetable(city: str) -> str:
    """Настоящая функция. Её выполняет ваш код."""
    return TIMETABLES.get(city, "нет данных по этому городу")


# ── А это всё, что модель знает про ваш код. Ровно три вещи. ─────────────────

TOOLS = [
    {
        "name": "read_timetable",
        "description": "Возвращает сырое расписание автобусов для указанного города.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Название города"},
            },
            "required": ["city"],
        },
    }
]


messages = [
    {"role": "user", "content": "Во сколько первый автобус 5А в Ярославле?"}
]


# ── Весь агентский цикл. Целиком. ───────────────────────────────────────────

for turn in range(5):  # харнесс владеет остановкой, не модель
    # Запрос собираем отдельно, чтобы его можно было увидеть и записать.
    request = {
        "model": "claude-opus-5",
        "max_tokens": 4096,
        "tools": TOOLS,
        "messages": messages,
    }
    wire("ВАШ КОД → API", request)

    response = client.messages.create(**request)

    wire("API → ВАШ КОД", response)

    # Ответ модели кладём в переписку как есть: на следующем ходу
    # мы отправим её заново целиком. Модель ничего не помнит сама.
    messages.append({"role": "assistant", "content": response.content})

    # Наивная ветка: всё, что не tool_use, считаем «готово». Для урока сойдёт,
    # но в настоящем харнессе здесь разбор всех stop_reason: max_tokens обрезал
    # ответ на полуслове, refusal — модель отказалась, pause_turn — серверный
    # цикл просит продолжить. Показать полный список своего SDK:
    #   python3 -c "import typing,anthropic.types as t;print(typing.get_args(t.StopReason))"
    if response.stop_reason != "tool_use":
        text = "".join(b.text for b in response.content if b.type == "text")
        print("ОТВЕТ:", text)
        break

    results = []
    for block in response.content:
        if block.type == "tool_use":
            print(f"МОДЕЛЬ ПРОСИТ: {block.name}({block.input})")

            output = read_timetable(**block.input)  # ← здесь работает ваш код

            print(f"read_timetable ВЕРНУЛ: {output!r}")
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,  # ниточка к конкретной просьбе
                    "content": output,
                }
            )

    messages.append({"role": "user", "content": results})

else:
    raise RuntimeError("модель не уложилась в 5 ходов")
