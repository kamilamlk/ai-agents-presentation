"""
RAG on a free model: search is just one more tool in the harness.

    export GROQ_API_KEY=gsk_...
    python3 free/example_rag.py

Two questions: the first is answerable from the documents, the second is not.
The code requires the model to cite a source that was actually retrieved, which
is the check here -- and on a smaller model it earns its keep more often.

ask() takes the call so it can be tested with a fake. See test_free.py.
"""

import json
import re

from wire import arguments, create, spent, text

DOCS = {
    "d1": "The timetable service refreshes its data once a day, at 04:00 UTC.",
    "d2": "The timetable service is owned by the transport team; on-call sits in #transport-duty.",
    "d3": "The timetable API is rate limited to 100 requests per minute per key.",
    "d4": "Over the limit the API replies with status 429 and a Retry-After header.",
}

SYSTEM = """Answer only from the retrieved fragments. Never fill in the gaps yourself.
Search before you answer.

End with a ```json block shaped like {"answer": "text", "source": "d1"}.
If the fragments do not contain the answer, return {"answer": null, "source": null}."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Searches internal documentation. Returns fragments with their ids.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
]


def words(text_):
    return set(re.findall(r"\w+", text_.lower()))


def search(query):
    """Word-overlap search. No vectors on purpose: the same pitfalls, no dependencies."""
    scored = sorted(
        ((len(words(query) & words(text_)), i, text_) for i, text_ in DOCS.items()),
        reverse=True,
    )
    return [(i, text_) for score, i, text_ in scored[:2] if score]


def check(result, found):
    """An answer must rest on a fragment that was actually retrieved."""
    if result["answer"] is None:
        return None
    if result["source"] not in found:
        return f"source {result['source']!r} is not among the retrieved {sorted(found)}"
    return None


def ask(question, call=create, log=print):
    log(f"\nQUESTION  {question}")
    messages = [{"role": "user", "content": question}]
    found = set()

    for _ in range(6):
        message, finish_reason = call(messages, tools=TOOLS, system=SYSTEM)
        messages.append(message)

        if finish_reason == "tool_calls":
            for tool_call in message["tool_calls"]:
                query = arguments(tool_call).get("query", "")
                hits = search(query)
                found.update(i for i, _ in hits)
                log(f"search    {query!r} -> {[i for i, _ in hits] or 'nothing'}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": "\n".join(f"[{i}] {t}" for i, t in hits) or "nothing found",
                })
            continue

        block = re.search(r"```json\s*(.*?)\s*```", text(message), re.S)
        if not block:
            log(f"code      rejected: no json block in {text(message)[:80]!r}")
            messages.append({"role": "user", "content": "Return the ```json block."})
            continue
        result = json.loads(block.group(1))

        problem = check(result, found)
        if problem:
            log(f"code      rejected: {problem}")
            messages.append({"role": "user",
                             "content": f"Not good: {problem}. Return the JSON again."})
            continue

        if result["answer"] is None:
            log("model     the sources do not contain the answer")
        else:
            log(f"model     {result['answer']}  [{result['source']}]")
        return result

    log("loop      gave up; a human gets it")
    return None


if __name__ == "__main__":
    ask("When is the timetable data refreshed?")
    ask("How much does access to the timetable API cost?")
    print(f"\nspent     {spent()}")
