"""
A harness on a free model: the model proposes, the code verifies and decides.

    export GROQ_API_KEY=gsk_...
    python3 free/example_harness.py
    python3 free/example_harness.py "When does 5A leave Chorsu?"

Line for line the same lesson as examples/example_harness.py, and check() is
copied from it unchanged -- that is the part that does not care which model
answered. The last trip crosses midnight. If the model writes 00:05, copied from
the timetable as printed, the code notices the times stopped increasing and
sends it back with the reason.

Rehearse this one before you show it. The free model is smaller: it may copy
00:05 and be corrected, it may write 24:05 straight away, and it may need the
retry twice. All three are honest outcomes of the same five lines -- but decide
which one you are narrating before you are standing in front of the room.

The loop lives in run(call) so it can be tested with a fake. See test_free.py.
"""

import json
import re
import sys

from wire import arguments, create, spent, text

TIMETABLE = """Route 5A -- weekdays
stop                 trip 1  trip 2  trip 3
Vokzal                06:15   23:05   23:40
Mustaqillik Maydoni   06:22   23:12   23:47
Chorsu                06:30   23:20   00:05"""

SYSTEM = 'End your answer with a ```json block shaped like {"times": ["06:15", "06:47"]}'

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_timetable",
            "description": "Raw bus timetable for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
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


def run(call=create, question=QUESTION, log=print):
    log(f"\nQUESTION  {question}")
    messages = [{"role": "user", "content": question}]

    for _ in range(6):
        message, finish_reason = call(messages, tools=TOOLS, system=SYSTEM)
        messages.append(message)

        if finish_reason not in ("tool_calls", "stop"):
            raise RuntimeError(f"unexpected finish_reason: {finish_reason}")

        if finish_reason == "tool_calls":
            for tool_call in message["tool_calls"]:
                log(f"model     asks for {tool_call['function']['name']}"
                    f"({tool_call['function']['arguments']})")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": read_timetable(**arguments(tool_call)),
                })
            continue

        block = re.search(r"```json\s*(.*?)\s*```", text(message), re.S)
        if not block:
            raise RuntimeError(f"no json block in the answer: {text(message)[:120]!r}")
        times = json.loads(block.group(1))["times"]
        log(f"model     proposes {', '.join(times) or 'nothing'}")

        problem = check(times)
        if not problem:
            log(f"code      accepted: {', '.join(times) or 'nothing'}")
            log(f"spent     {spent()}")
            return times

        log(f"code      rejected: {problem}")
        messages.append({"role": "user",
                         "content": f"Not good: {problem}. Return the JSON again."})

    raise RuntimeError("did not finish within the allotted turns")


if __name__ == "__main__":
    run(question=" ".join(sys.argv[1:]) or QUESTION)
