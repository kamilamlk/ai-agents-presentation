"""
example_cost.py — тот же агент, что и example_tool_loop.py, но с ценником.

После каждого хода печатает, сколько токенов ушло на вход, сколько пришло
на выход, сколько из выхода составило скрытое размышление, и во что это обошлось.

Запуск:
    source ./anthropic-env.sh on
    python3 example_cost.py

Что увидеть глазами:
  1. Вход на втором ходу больше, чем на первом, хотя вопрос не менялся:
     это выросла переписка, и вы платите за неё заново.
  2. Выход меньше входа по количеству, но сопоставим по деньгам:
     он в пять раз дороже за токен.
"""

import anthropic

client = anthropic.Anthropic()

MODEL = "claude-opus-5"

# Прайс в долларах за 1 000 000 токенов. Проверяйте перед докладом: цены меняются.
PRICE_IN = 5.00
PRICE_OUT = 25.00

# Множители кэша: запись дороже обычного входа, чтение сильно дешевле.
CACHE_WRITE_MULT = 1.25   # 5-минутный TTL
CACHE_READ_MULT = 0.10


TIMETABLES = {
    "Ярославль": "5А: 06:15, 06:47, 07:20, 07:53 | 21: 05:58, 06:30, 07:02",
    "Кострома": "3: 06:05, 06:40, 07:15 | 11: 06:22, 07:00",
}


def read_timetable(city: str) -> str:
    return TIMETABLES.get(city, "нет данных по этому городу")


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


def money(usage) -> float:
    """Цена одного ответа в долларах.

    Внимание на input_tokens: это НЕ весь промпт, а только та его часть,
    которая не попала в кэш. Полный размер промпта складывается из трёх полей.
    """
    fresh = usage.input_tokens
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0

    return (
        fresh * PRICE_IN
        + written * PRICE_IN * CACHE_WRITE_MULT
        + read * PRICE_IN * CACHE_READ_MULT
        + usage.output_tokens * PRICE_OUT
    ) / 1_000_000


messages = [
    {"role": "user", "content": "Во сколько первый автобус 5А в Ярославле?"}
]

rows = []

for turn in range(5):
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=TOOLS,
        messages=messages,
    )
    u = response.usage
    rows.append(
        {
            "ход": len(rows) + 1,
            "вход": u.input_tokens,
            "выход": u.output_tokens,
            "думал": getattr(u.output_tokens_details, "thinking_tokens", 0)
            if getattr(u, "output_tokens_details", None)
            else 0,
            "цена": money(u),
        }
    )

    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        answer = "".join(b.text for b in response.content if b.type == "text")
        break

    results = []
    for block in response.content:
        if block.type == "tool_use":
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": read_timetable(**block.input),
                }
            )
    messages.append({"role": "user", "content": results})
else:
    raise RuntimeError("модель не уложилась в 5 ходов")


print(f"\n{'ХОД':>4} {'ВХОД':>7} {'ВЫХОД':>7} {'ДУМАЛ':>7} {'ЦЕНА':>11}")
print("─" * 40)
for r in rows:
    print(f"{r['ход']:>4} {r['вход']:>7} {r['выход']:>7} {r['думал']:>7} {'$%.5f' % r['цена']:>11}")
print("─" * 40)
print(
    f"{'ИТОГО':>4} {sum(r['вход'] for r in rows):>7} {sum(r['выход'] for r in rows):>7}"
    f" {sum(r['думал'] for r in rows):>7} {'$%.5f' % sum(r['цена'] for r in rows):>11}"
)

vhod = sum(r["вход"] for r in rows) * PRICE_IN / 1e6
vyhod = sum(r["выход"] for r in rows) * PRICE_OUT / 1e6
print(f"\nиз них за чтение: ${vhod:.5f}   за письмо: ${vyhod:.5f}")
print(f"\nОТВЕТ: {answer}")
