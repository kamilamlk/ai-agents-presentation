"""
Харнесс: модель предлагает, код проверяет и решает.

    source ./anthropic-env.sh on
    python3 example_harness.py

В расписании есть рейс через полночь. Модель выпишет 00:15 — правдоподобно
и неверно. Код заметит, что времена перестали расти, и отправит исправлять.

Цикл вынесен в функцию run(client), чтобы его можно было протестировать
с поддельным клиентом. См. test_harness.py.
"""

import json
import re

import anthropic

TIMETABLE = "5А: 23:05, 23:40, 00:15"

SYSTEM = 'Ответ заканчивай блоком ```json вида {"times": ["06:15", "06:47"]}'

TOOLS = [
    {
        "name": "read_timetable",
        "description": "Сырое расписание автобусов города.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    }
]


def read_timetable(city):
    return TIMETABLE


def check(times):
    """Проверка кодом. Стоит ноль и всегда отвечает одинаково."""
    for a, b in zip(times, times[1:]):
        if b <= a:
            return f"{a} идёт перед {b}, времена должны расти. За полночь пиши 24:15, а не 00:15"
    return None


def run(client, question="Выпиши времена рейса 5А в Ярославле.", log=print):
    messages = [{"role": "user", "content": question}]

    for _ in range(6):
        r = client.messages.create(
            model="claude-opus-5", max_tokens=2048,
            system=SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": r.content})

        if r.stop_reason not in ("tool_use", "end_turn"):
            raise RuntimeError(f"неожиданный stop_reason: {r.stop_reason}")

        if r.stop_reason == "tool_use":
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    log(f"модель  просит {b.name}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": read_timetable(**b.input),
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in r.content if b.type == "text")
        times = json.loads(re.search(r"```json\s*(.*?)\s*```", text, re.S).group(1))["times"]
        log(f"модель  предлагает {times}")

        problem = check(times)
        if not problem:
            log(f"код     принял {times}")
            return times

        log(f"код     отклонил: {problem}")
        messages.append({"role": "user", "content": f"Не годится: {problem}. Верни JSON заново."})

    raise RuntimeError("не уложились в отведённые круги")


if __name__ == "__main__":
    run(anthropic.Anthropic())
