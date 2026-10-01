"""
Tests for the harness. Not a single API call, not a single token spent.

    python3 test_harness.py

The model is replaced by a stub that returns pre-recorded replies.
"""

import copy
import json
from types import SimpleNamespace as NS

from example_harness import check, run


# -- The fake model ---------------------------------------------------------

def text_block(t):
    return NS(type="text", text=t)


def tool_block(name, **kwargs):
    return NS(type="tool_use", id="toolu_fake", name=name, input=kwargs)


def reply(stop_reason, *blocks):
    return NS(stop_reason=stop_reason, content=list(blocks))


def answer(times):
    body = json.dumps({"times": list(times)})
    return reply("end_turn", text_block(f"```json\n{body}\n```"))


class FakeClient:
    """Returns prepared replies in order and remembers what it was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []
        self.messages = self

    def create(self, **kw):
        # The snapshot is mandatory: messages is mutated as the loop runs, and
        # without a copy every entry in self.sent would point at one final state.
        self.sent.append({**kw, "messages": copy.deepcopy(kw["messages"])})
        return self.replies.pop(0)


def quiet(*a, **kw):
    pass


# -- check(): a pure function, no model involved at all ---------------------

def test_check_accepts_increasing():
    assert check(["06:15", "06:22", "06:30"]) is None


def test_check_catches_the_midnight_step_backwards():
    assert "23:47" in check(["23:40", "23:47", "00:05"])


def test_check_catches_duplicates():
    assert check(["06:15", "06:15"]) is not None


def test_check_survives_single_item():
    assert check(["06:15"]) is None


# -- The loop: fake model, every branch exercised --------------------------

def test_tool_called_and_result_returned():
    c = FakeClient(
        reply("tool_use", tool_block("read_timetable", city="Tashkent")),
        answer(["23:40", "23:47", "24:05"]),
    )
    run(c, log=quiet)

    second = c.sent[1]["messages"][-1]
    assert second["role"] == "user"
    assert second["content"][0]["type"] == "tool_result"
    assert "5A" in second["content"][0]["content"]


def test_retry_after_failed_check():
    c = FakeClient(
        answer(["23:40", "23:47", "00:05"]),   # the model copied the printed time
        answer(["23:40", "23:47", "24:05"]),   # and worked out the convention
    )
    assert run(c, log=quiet) == ["23:40", "23:47", "24:05"]
    assert len(c.sent) == 2
    assert "Not good" in c.sent[1]["messages"][-1]["content"]


def test_good_answer_accepted_first_time():
    c = FakeClient(answer(["06:15", "06:22", "06:30"]))
    assert run(c, log=quiet) == ["06:15", "06:22", "06:30"]
    assert len(c.sent) == 1


def test_loop_is_not_infinite():
    c = FakeClient(*[answer(["09:00", "08:00"]) for _ in range(6)])
    try:
        run(c, log=quiet)
    except RuntimeError:
        return
    raise AssertionError("the loop should have given up")


def test_truncated_answer_is_not_success():
    c = FakeClient(reply("max_tokens", text_block("```json")))
    try:
        run(c, log=quiet)
    except RuntimeError as e:
        assert "max_tokens" in str(e)
        return
    raise AssertionError("a truncated answer must fail, not be accepted")


# -- Runner ----------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"ok     {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAILED {t.__name__}: {e}")
    print(f"\n{len(tests) - failed} of {len(tests)} passed")
