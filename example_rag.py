"""
RAG: поиск — это просто ещё один инструмент харнесса.

    source ./anthropic-env.sh on
    python3 example_rag.py

Два вопроса: на первый ответ в документах есть, на второй нет.
Код требует, чтобы модель указала источник из реально найденного.
"""

import json
import re

import anthropic

client = anthropic.Anthropic()

DOCS = {
    "d1": "Сервис расписаний обновляет данные раз в сутки, в 04:00 по Москве.",
    "d2": "За сервис расписаний отвечает команда транспорта, дежурный в чате transport-duty.",
    "d3": "Лимит запросов к API расписаний — 100 в минуту на один ключ.",
    "d4": "При превышении лимита API отвечает кодом 429 и заголовком Retry-After.",
}

SYSTEM = """Отвечай только по найденным фрагментам, ничего не додумывай.

Заканчивай блоком ```json вида {"answer": "текст", "source": "d1"}.
Если ответа во фрагментах нет — {"answer": null, "source": null}."""

TOOLS = [
    {
        "name": "search_docs",
        "description": "Ищет во внутренней документации. Возвращает фрагменты с их id.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
]


def words(text):
    return set(re.findall(r"\w+", text.lower()))


def search(query):
    """Поиск по совпадению слов. Векторов нет специально: грабли те же."""
    scored = sorted(
        ((len(words(query) & words(text)), i, text) for i, text in DOCS.items()),
        reverse=True,
    )
    return [(i, text) for score, i, text in scored[:2] if score]


def check(result, found):
    """Ответ обязан опираться на найденный фрагмент."""
    if result["answer"] is None:
        return None
    if result["source"] not in found:
        return f"источник {result['source']!r} не из найденных {sorted(found)}"
    return None


def ask(question):
    print(f"\nВОПРОС  {question}")
    messages = [{"role": "user", "content": question}]
    found = set()

    for _ in range(6):
        r = client.messages.create(
            model="claude-opus-5", max_tokens=2048,
            system=SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": r.content})

        if r.stop_reason == "tool_use":
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    hits = search(**b.input)
                    found.update(i for i, _ in hits)
                    print(f"поиск   {b.input['query']!r} -> {[i for i, _ in hits] or 'ничего'}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": "\n".join(f"[{i}] {t}" for i, t in hits) or "ничего не найдено",
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in r.content if b.type == "text")
        result = json.loads(re.search(r"```json\s*(.*?)\s*```", text, re.S).group(1))

        problem = check(result, found)
        if problem:
            print(f"код     отклонил: {problem}")
            messages.append({"role": "user", "content": f"Не годится: {problem}. Верни JSON заново."})
            continue

        if result["answer"] is None:
            print("модель  ответа в источниках нет")
        else:
            print(f"модель  {result['answer']}  [{result['source']}]")
        return


ask("Во сколько обновляются данные расписаний?")
ask("Сколько стоит доступ к API расписаний?")
