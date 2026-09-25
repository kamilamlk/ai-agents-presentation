"""
A harness: the model proposes, the code verifies and decides.

    source ./anthropic-env.sh on
    python3 example_harness.py

The timetable contains a trip that runs past midnight. The model will write
00:15 -- plausible and wrong. The code notices that the times stopped increasing
and sends it back to be fixed.

The loop lives in run(client) so it can be tested with a fake client.
See test_harness.py.
"""

import json
import re

import anthropic

TIMETABLE = "5A: 23:05, 23:40, 00:15"

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


def read_timetable(city):
    return TIMETABLE


def check(times):
    """Verification in code. Costs nothing and always answers the same."""
    for a, b in zip(times, times[1:]):
        if b <= a:
            return f"{a} comes before {b}; times must increase. Past midnight write 24:15, not 00:15"
    return None


def run(client, question="List the times of route 5A in Yaroslavl.", log=print):
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
                    log(f"model  asks for {b.name}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": read_timetable(**b.input),
                    })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(b.text for b in r.content if b.type == "text")
        times = json.loads(re.search(r"```json\s*(.*?)\s*```", text, re.S).group(1))["times"]
        log(f"model  proposes {times}")

        problem = check(times)
        if not problem:
            log(f"code   accepted {times}")
            return times

        log(f"code   rejected: {problem}")
        messages.append({"role": "user", "content": f"Not good: {problem}. Return the JSON again."})

    raise RuntimeError("did not finish within the allotted turns")


if __name__ == "__main__":
    run(anthropic.Anthropic())
