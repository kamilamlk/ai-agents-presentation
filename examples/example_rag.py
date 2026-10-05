"""
RAG: search is just one more tool in the harness.

    source ./anthropic-env.sh on
    python3 example_rag.py

Two questions: the first is answerable from the documents, the second is not.
The code requires the model to cite a source that was actually retrieved.
"""

import json
import re

import anthropic

client = anthropic.Anthropic()

DOCS = {
    "d1": "The timetable service refreshes its data once a day, at 04:00 UTC.",
    "d2": "The timetable service is owned by the transport team; on-call sits in #transport-duty.",
    "d3": "The timetable API is rate limited to 100 requests per minute per key.",
    "d4": "Over the limit the API replies with status 429 and a Retry-After header.",
}

SYSTEM = """Answer only from the retrieved fragments. Never fill in the gaps yourself.

End with a ```json block shaped like {"answer": "text", "source": "d1"}.
If the fragments do not contain the answer, return {"answer": null, "source": null}."""

TOOLS = [
    {
        "name": "search_docs",
        "description": "Searches internal documentation. Returns fragments with their ids.",
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
    """Word-overlap search. No vectors on purpose: the same pitfalls, no dependencies."""
    scored = sorted(
        ((len(words(query) & words(text)), i, text) for i, text in DOCS.items()),
        reverse=True,
    )
    return [(i, text) for score, i, text in scored[:2] if score]


def check(result, found):
    """An answer must rest on a fragment that was actually retrieved."""
    if result["answer"] is None:
        return None
    if result["source"] not in found:
        return f"source {result['source']!r} is not among the retrieved {sorted(found)}"
    return None


def ask(question):
    print(f"\nQUESTION  {question}")
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
                    print(f"search    {b.input['query']!r} -> {[i for i, _ in hits] or 'nothing'}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": "\n".join(f"[{i}] {t}" for i, t in hits) or "nothing found",
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in r.content if b.type == "text")
        result = json.loads(re.search(r"```json\s*(.*?)\s*```", text, re.S).group(1))

        problem = check(result, found)
        if problem:
            print(f"code      rejected: {problem}")
            messages.append({"role": "user", "content": f"Not good: {problem}. Return the JSON again."})
            continue

        if result["answer"] is None:
            print("model     the sources do not contain the answer")
        else:
            print(f"model     {result['answer']}  [{result['source']}]")
        return


ask("When is the timetable data refreshed?")
ask("How much does access to the timetable API cost?")
