"""
example_cache.py — то же самое, но с кэшем промпта, и с замером выгоды.

Гоняет один и тот же запрос три раза подряд. Это имитация харнесса, который
вызывает модель на каждой странице PDF: инструкция и описания инструментов
от страницы к странице не меняются, меняется только сам вопрос.

Запуск:
    source ./anthropic-env.sh on
    python3 example_cache.py

Что увидеть глазами:
  прогон 1 — cache_creation больше нуля: кэш записан, заплатили 1.25x
  прогон 2 — cache_read больше нуля:     кэш прочитан, заплатили 0.10x
  прогон 3 — то же самое

ВАЖНО ПРО МИНИМУМ. Кэшируемый префикс должен быть не короче 512 токенов
(на Claude Opus 5; на других моделях минимум другой и не всегда меньше).
Более короткий префикс не кэшируется МОЛЧА: ошибки не будет, просто в usage
останутся нули. Одних только TOOLS в этом примере не хватает: они весят
около 378 токенов. Поэтому добавлен системный промпт, и вместе они проходят
порог. Скрипт проверяет это сам и скажет, если кэш не сработал.

Точка разреза стоит на системном блоке, а не на инструментах, потому что
порядок сборки промпта такой: tools, затем system, затем messages.
Разрез на system накрывает и то и другое.
"""

import anthropic

client = anthropic.Anthropic()

MODEL = "claude-opus-5"
PRICE_IN = 5.00
PRICE_OUT = 25.00
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10
MIN_CACHEABLE = 512

RUNS = 3


SYSTEM = """Ты извлекаешь расписания общественного транспорта.

Правила разбора:
- Время всегда приводи к формату HH:MM:SS.
- Рейсы после полуночи записывай как 25:10:00, а не как 01:10:00: в GTFS
  сервисный день продолжается за полночь, и подмена уводит рейс в другие сутки.
- Если в источнике несколько маршрутов, разбирай их по отдельности и не
  смешивай времена между ними.
- Сноски вида «только по будням» относятся к календарю, а не ко времени.
- Если данных для города нет, так и скажи, ничего не придумывай.
- Никогда не выдумывай остановки, которых нет в источнике.
- Отвечай кратко, без предисловий и без пересказа этих правил."""


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

# Вот он, единственный содержательный отличающий момент: точка разреза кэша.
SYSTEM_CACHED = [
    {
        "type": "text",
        "text": SYSTEM,
        "cache_control": {"type": "ephemeral"},
    }
]


def parts(usage):
    """Три составляющие промпта. input_tokens это только некэшированный остаток."""
    fresh = usage.input_tokens
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return fresh, written, read


def money(usage) -> float:
    fresh, written, read = parts(usage)
    return (
        fresh * PRICE_IN
        + written * PRICE_IN * CACHE_WRITE_MULT
        + read * PRICE_IN * CACHE_READ_MULT
        + usage.output_tokens * PRICE_OUT
    ) / 1_000_000


def money_without_cache(usage) -> float:
    """Во что обошёлся бы тот же запрос, если бы кэша не было вовсе."""
    fresh, written, read = parts(usage)
    return ((fresh + written + read) * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1_000_000


def one_run():
    """Полный круг диалога. Возвращает список usage всех ответов."""
    messages = [
        {"role": "user", "content": "Во сколько первый автобус 5А в Ярославле?"}
    ]
    used = []

    for _ in range(5):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_CACHED,
            tools=TOOLS,
            messages=messages,
        )
        used.append(response.usage)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return used

        results = [
            {
                "type": "tool_result",
                "tool_use_id": b.id,
                "content": read_timetable(**b.input),
            }
            for b in response.content
            if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})

    raise RuntimeError("модель не уложилась в 5 ходов")


print(f"\n{'ПРОГОН':>7} {'СВЕЖИХ':>8} {'ЗАПИСЬ':>8} {'ЧТЕНИЕ':>8} {'ВЫХОД':>7} {'С КЭШЕМ':>10} {'БЕЗ КЭША':>10}")
print("─" * 64)

total_cached = total_plain = 0.0
g_fresh = g_written = g_read = g_out = 0

for run in range(1, RUNS + 1):
    used = one_run()
    fresh = sum(parts(u)[0] for u in used)
    written = sum(parts(u)[1] for u in used)
    read = sum(parts(u)[2] for u in used)
    out = sum(u.output_tokens for u in used)
    c = sum(money(u) for u in used)
    p = sum(money_without_cache(u) for u in used)

    total_cached += c
    total_plain += p
    g_fresh += fresh
    g_written += written
    g_read += read
    g_out += out

    print(f"{run:>7} {fresh:>8} {written:>8} {read:>8} {out:>7} {'$%.5f' % c:>10} {'$%.5f' % p:>10}")

print("─" * 64)
print(f"{'ИТОГО':>7} {'':>8} {'':>8} {'':>8} {'':>7} {'$%.5f' % total_cached:>10} {'$%.5f' % total_plain:>10}")

prompt_total = g_fresh + g_written + g_read

print("\nКАК ЭТО ПОСЧИТАНО, итогом по всем прогонам")
print(f"  свежий вход  {g_fresh:>6} × ${PRICE_IN}/1M × 1.00  = ${g_fresh * PRICE_IN / 1e6:.5f}")
print(f"  запись       {g_written:>6} × ${PRICE_IN}/1M × {CACHE_WRITE_MULT:.2f}  = ${g_written * PRICE_IN * CACHE_WRITE_MULT / 1e6:.5f}")
print(f"  чтение       {g_read:>6} × ${PRICE_IN}/1M × {CACHE_READ_MULT:.2f}  = ${g_read * PRICE_IN * CACHE_READ_MULT / 1e6:.5f}")
print(f"  выход        {g_out:>6} × ${PRICE_OUT}/1M         = ${g_out * PRICE_OUT / 1e6:.5f}")
print(f"  {'':>13}{'':>6}{'':>21}  ─────────")
print(f"  с кэшем      {'':>6}{'':>21}  ${total_cached:.5f}")
print()
print(f"  Весь промпт целиком: {g_fresh} + {g_written} + {g_read} = {prompt_total} токенов.")
print(f"  Без кэша те же {prompt_total} шли бы по полной ставке:")
print(f"  {prompt_total} × ${PRICE_IN}/1M + {g_out} × ${PRICE_OUT}/1M = ${total_plain:.5f}")
print("  Второй прогон для этого не нужен: токены измерены, гипотетическая только ставка.")

if g_written == 0 and g_read == 0:
    print(
        f"\nКЭШ НЕ СРАБОТАЛ. Ни записи, ни чтения. Самая частая причина: префикс "
        f"короче {MIN_CACHEABLE} токенов, порог у модели {MODEL}. "
        f"Ошибки при этом не будет никогда, только нули в usage."
    )
else:
    saved = total_plain - total_cached
    pct = saved / total_plain * 100 if total_plain else 0
    print(f"\nЭкономия за {RUNS} прогона: ${saved:.5f}, это {pct:.0f}%.")
    if g_written > 0:
        print("Первый прогон дороже: запись в кэш стоит 1.25x. Окупается со второго.")
    else:
        print(
            "Записи не было ни разу: префикс уже лежал в кэше от прошлого запуска. "
            f"Запись живёт 5 минут — подожди столько же и запусти снова, чтобы увидеть её."
        )
