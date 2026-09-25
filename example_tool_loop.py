"""
The smallest agent that can possibly exist.
One tool, one question, four messages over the wire.

Run:
    pip3 install anthropic
    source ./anthropic-env.sh on
    python3 example_tool_loop.py

Credentials are picked up from the environment, no code changes needed. The SDK
resolves them in this order: ANTHROPIC_API_KEY, then ANTHROPIC_AUTH_TOKEN, then
the `ant auth login` profile. First match wins.

  - direct Anthropic key -> ANTHROPIC_API_KEY (sent as the x-api-key header)
  - corporate gateway    -> ANTHROPIC_AUTH_TOKEN (sent as Authorization: Bearer)
                            PLUS ANTHROPIC_BASE_URL, or the request goes to
                            api.anthropic.com and fails

A gateway may expose a different set of models. Check with:
    python3 -c "import anthropic; [print(m.id) for m in anthropic.Anthropic().models.list()]"
If claude-opus-5 is not listed, use an id that is.

Three things to point at when showing this file:
  1. The model never sees TIMETABLES. It sees TOOLS: a name, a description, a schema.
  2. `output = read_timetable(**block.input)` is the only line where anything
     actually happens. Your code runs it, not the model.
  3. `range(5)` is what "the harness owns termination" means.

After a run you get wire.json next to this file: a plain formatted JSON array of
every message in order. Open it in any editor. It is rewritten on every turn, so
it stays valid even if the run dies halfway.

HTTP-level diagnostics (method, URL, status, request_id, retries) come from an
environment variable. It does not show response bodies:

    ANTHROPIC_LOG=debug python3 example_tool_loop.py
"""

import json
import pathlib

import anthropic

client = anthropic.Anthropic()


# -- Wire log: everything sent and received, as readable JSON ----------------
#
# Bodies only. Headers are never logged: that is where the token lives, and it
# belongs neither in a file nor on a projector.

WIRE = pathlib.Path("wire.json")
_exchange: list = []


def wire(direction: str, payload: object) -> None:
    def encode(o: object) -> object:
        return o.model_dump(mode="json") if hasattr(o, "model_dump") else str(o)

    # Snapshot immediately: payload holds a reference to the messages list, which
    # keeps growing. Without the round-trip the log would show a future state of
    # the conversation rather than what was actually sent on this turn.
    snapshot = json.loads(json.dumps({"direction": direction, "payload": payload}, default=encode))

    _exchange.append(snapshot)
    WIRE.write_text(json.dumps(_exchange, ensure_ascii=False, indent=2), encoding="utf-8")


# -- Your data. The model will never see this. ------------------------------

TIMETABLES = {
    "Yaroslavl": "5A: 06:15, 06:47, 07:20, 07:53 | 21: 05:58, 06:30, 07:02",
    "Kostroma": "3: 06:05, 06:40, 07:15 | 11: 06:22, 07:00",
}


def read_timetable(city: str) -> str:
    """A real function. Your code runs it."""
    return TIMETABLES.get(city, "no data for this city")


# -- And this is everything the model knows about your code. Three things. ---

TOOLS = [
    {
        "name": "read_timetable",
        "description": "Returns the raw bus timetable for a given city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
            },
            "required": ["city"],
        },
    }
]


messages = [
    {"role": "user", "content": "What time is the first 5A bus in Yaroslavl?"}
]


# -- The whole agent loop. All of it. ---------------------------------------

for turn in range(5):  # the harness owns termination, not the model
    # The request is built separately so it can be seen and logged.
    request = {
        "model": "claude-opus-5",
        "max_tokens": 4096,
        "tools": TOOLS,
        "messages": messages,
    }
    wire("YOUR CODE -> API", request)

    response = client.messages.create(**request)

    wire("API -> YOUR CODE", response)

    # The model's reply goes into the conversation as-is: on the next turn we
    # send the whole thing again. The model remembers nothing by itself.
    messages.append({"role": "assistant", "content": response.content})

    # Naive branch: anything that is not tool_use counts as "done". Fine for a
    # lesson, but a real harness handles every stop_reason: max_tokens truncated
    # the answer, refusal means the model declined, pause_turn means the server
    # loop wants to continue. To list what your SDK knows:
    #   python3 -c "import typing,anthropic.types as t;print(typing.get_args(t.StopReason))"
    if response.stop_reason != "tool_use":
        text = "".join(b.text for b in response.content if b.type == "text")
        print("ANSWER:", text)
        break

    results = []
    for block in response.content:
        if block.type == "tool_use":
            print(f"MODEL ASKS FOR: {block.name}({block.input})")

            output = read_timetable(**block.input)  # <- your code runs here

            print(f"YOUR CODE RETURNED: {output!r}")
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,  # the thread back to this request
                    "content": output,
                }
            )

    messages.append({"role": "user", "content": results})

else:
    raise RuntimeError("the model did not finish within 5 turns")
