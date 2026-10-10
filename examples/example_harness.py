"""
A harness: the model proposes, the code verifies and decides.

    source ./anthropic-env.sh on
    python3 example_harness.py
    python3 example_harness.py "When does 5A leave Chorsu?"

The last trip crosses midnight. The model writes 00:05 -- copied from the
timetable as printed, well-formed, and wrong: along a trip the clock only moves
forward, so the service day continues into 24:05. The code notices the times
stopped increasing and sends it back with the reason.

Yes, that rule could have gone in the system prompt instead. You would have had
to know it first. Every rule in a system prompt is a mistake somebody already
made -- this is the code that finds the next one.

The loop lives in run(client) so it can be tested with a fake client.
See test_harness.py.
"""

import json
import re
import sys

import anthropic

TIMETABLE = """Route 5A -- weekdays
stop                 trip 1  trip 2  trip 3
Vokzal                06:15   23:05   23:40
Mustaqillik Maydoni   06:22   23:12   23:47
Chorsu                06:30   23:20   00:05"""

SYSTEM = 'End your answer with a ```json block shaped like {"times": ["06:15", "06:47"]}'

TOOLS = [
    {
        "name": "read_timetable",
        "description": "Raw bus timetable for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    }
]

QUESTION = "List the times of the last trip of route 5A in Tashkent."


def read_timetable(city):
    return TIMETABLE


def check(times):
    """Verification in code. Costs nothing and always answers the same."""
    for a, b in zip(times, times[1:]):
        if b <= a:
            h, m = b.split(":")
            return (f"{a} comes before {b}: times must increase along the trip. "
                    f"A service day continues past midnight, so write {int(h) + 24}:{m}")
    return None


def run(client, question=QUESTION, log=print):
    log(f"\nQUESTION  {question}")
    messages = [{"role": "user", "content": question}]

    for _ in range(6):
        r = client.messages.create(
            model="claude-opus-5", max_tokens=2048,
            system=SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": r.content})

        if r.stop_reason not in ("tool_use", "end_turn"):
            raise RuntimeError(f"unexpected stop_reason: {r.stop_reason}")

        if r.stop_reason == "tool_use":
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    if b.name == "read_timetable":  
                        log(f"model     asks for {b.name}({b.input})")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": read_timetable(**b.input),
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in r.content if b.type == "text")
        times = json.loads(re.search(r"```json\s*(.*?)\s*```", text, re.S).group(1))["times"]
        log(f"model     proposes {', '.join(times) or 'nothing'}")

        problem = check(times)
        if not problem:
            log(f"code      accepted: {', '.join(times) or 'nothing'}")
            return times

        log(f"code      rejected: {problem}")
        messages.append({"role": "user", "content": f"Not good: {problem}. Return the JSON again."})

    raise RuntimeError("did not finish within the allotted turns")


if __name__ == "__main__":
    run(anthropic.Anthropic(), " ".join(sys.argv[1:]) or QUESTION)
