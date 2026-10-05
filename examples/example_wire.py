"""
Every request and every response body of a harness run, written to disk as JSON.

    source ./anthropic-env.sh on
    python3 example_wire.py
    python3 example_wire.py "When does 5A leave Chorsu?"

There is no second loop here. The loop is the one in example_harness.py -- this
file only slips a recorder in where the client goes, the same seam the tests use
to slip in a fake. Four jobs of a harness, and this touches none of them.

    wire/round-1-request.json    what your code sent
    wire/round-1-response.json   what came back
    ...                          one pair per round, retries included
    wire/messages.json           the conversation at the end of the run
    wire/messages-0.json ...     one file per message

The rejection is in there too, as a message with role "user": when your code
disagrees with the model, that is the only way it can say so.

Bodies only. Headers are never written: that is where the token lives, and it
belongs neither in a file nor on a projector.
"""

import json
import pathlib
import sys

import anthropic

from example_harness import QUESTION, run

OUT = pathlib.Path("wire")


def trim(o: object) -> object:
    """Drop keys that came back null. An absent field has nothing to teach."""
    if isinstance(o, dict):
        return {k: trim(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [trim(v) for v in o]
    return o


def plain(payload: object) -> object:
    """Plain data, and a snapshot.

    The snapshot is the point: `payload` holds a reference to the messages list,
    which the loop keeps appending to. Store the reference instead and you get a
    future state of the conversation rather than what was sent this round.
    """

    def encode(o: object) -> object:
        return o.model_dump(mode="json") if hasattr(o, "model_dump") else str(o)

    return trim(json.loads(json.dumps(payload, default=encode)))


def dump(name: str, payload: object) -> pathlib.Path:
    """One body, one file, formatted so it can be screenshotted as it is."""
    path = OUT / f"{name}.json"
    path.write_text(
        json.dumps(plain(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote     {path}")
    return path


class Recorder:
    """Stands where the client stands, writes both bodies, forwards the call."""

    def __init__(self, client):
        self.client = client
        self.round = 0
        self.last_request = None
        self.last_response = None
        self.messages = self       # so recorder.messages.create(...) works

    def create(self, **kw):
        self.round += 1
        dump(f"round-{self.round}-request", kw)

        response = self.client.messages.create(**kw)

        dump(f"round-{self.round}-response", response)
        self.last_request = plain(kw)          # a snapshot, never the live list
        self.last_response = plain(response)
        return response


OUT.mkdir(exist_ok=True)

recorder = Recorder(anthropic.Anthropic())
run(recorder, " ".join(sys.argv[1:]) or QUESTION)

# The loop keeps the conversation to itself, so rebuild it: everything that went
# out on the last round, plus the reply that ended it.
conversation = list(recorder.last_request["messages"])
conversation.append({"role": "assistant", "content": recorder.last_response["content"]})

dump("messages", conversation)
for i, message in enumerate(conversation):
    dump(f"messages-{i}", message)

print(f"\n{len(conversation)} messages, {recorder.round} rounds over the wire")
