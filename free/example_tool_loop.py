"""
The smallest agent that can possibly exist, on a free model.
One tool, one question, four messages over the wire.

    export GROQ_API_KEY=gsk_...
    python3 free/example_tool_loop.py

The same file as examples/example_tool_loop.py, with the envelope swapped. Three
things to point at, and they are the same three:

  1. The model never sees TIMETABLES. It sees TOOLS: a name, a description, a schema.
  2. `output = read_timetable(**arguments(call))` is the only line where anything
     actually happens. Your code runs it, not the model.
  3. `range(5)` is what "the harness owns termination" means.

Two things that are genuinely different here:

  - No SDK, so no objects: the response is already a dict and goes into the log
    and back into the conversation as it arrived.
  - A tool result is its own message with role "tool", one per call, each tied
    back by tool_call_id. In the Anthropic shape it is a block inside a user
    message instead.

After a run you get wire_free.json next to the directory you ran from.
"""

import json
import pathlib

from wire import MODEL, arguments, create, spent, text

# -- Wire log: everything sent and received, as readable JSON ----------------
#
# Bodies only. Headers are never logged: that is where the token lives, and it
# belongs neither in a file nor on a projector.

WIRE = pathlib.Path("wire_free.json")
_exchange: list = []


def wire(direction, payload):
    # Nothing to convert: without an SDK there are no objects to dump, only the
    # dicts that went over the wire. Snapshot anyway -- messages keeps growing,
    # and the log must show this turn, not the final state of the conversation.
    _exchange.append(json.loads(json.dumps({"direction": direction, "payload": payload})))
    WIRE.write_text(json.dumps(_exchange, ensure_ascii=False, indent=2), encoding="utf-8")


# -- Your data. The model will never see this. ------------------------------

TIMETABLES = {
    "Tashkent": "5A: 06:15, 06:47, 07:20, 07:53 | 21: 05:58, 06:30, 07:02",
    "Samarkand": "3: 06:05, 06:40, 07:15 | 11: 06:22, 07:00",
}


def read_timetable(city):
    """A real function. Your code runs it."""
    return TIMETABLES.get(city, "no data for this city")


# -- And this is everything the model knows about your code. Three things. ---
#
# The same three, one wrapper deeper: "function" around them, and "parameters"
# where the Anthropic shape says "input_schema".

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_timetable",
            "description": "Returns the raw bus timetable for a given city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
        },
    }
]


messages = [
    {"role": "user", "content": "What time is the first 5A bus in Tashkent?"}
]


# -- The whole agent loop. All of it. ---------------------------------------

for turn in range(5):  # the harness owns termination, not the model
    wire("YOUR CODE -> API", {"model": MODEL, "tools": TOOLS, "messages": messages})

    message, finish_reason = create(messages, tools=TOOLS)

    wire("API -> YOUR CODE", {"finish_reason": finish_reason, "message": message})

    # The model's reply goes into the conversation as-is: on the next turn we
    # send the whole thing again. The model remembers nothing by itself.
    messages.append(message)

    # Naive branch: anything that is not a tool call counts as "done". Fine for
    # a lesson, but a real harness handles the rest -- "length" means the answer
    # was truncated, "content_filter" means it was refused.
    if finish_reason != "tool_calls":
        print("ANSWER:", text(message))
        print("SPENT: ", spent())
        break

    for call in message["tool_calls"]:
        print(f"MODEL ASKS FOR: {call['function']['name']}({call['function']['arguments']})")

        output = read_timetable(**arguments(call))  # <- your code runs here

        print(f"YOUR CODE RETURNED: {output!r}")

        # One message per call, each tied back by tool_call_id. Skip one and the
        # next request is rejected: every call must be answered.
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})

else:
    raise RuntimeError("the model did not finish within 5 turns")
